from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Optional

from src.chat.base import Intent, IntentRoute

# Lightweight, deterministic query routing for the chat assistant. No LLM is
# required to understand a question: keyword + regex rules classify intent and
# pull parameters (top-N, score thresholds, priority bands, platform, place).
# Extracted values always go through the search engine's filter whitelist
# later, so nothing user-supplied reaches SQL unvalidated.


_PRIORITY_BANDS = {
    "hot": "Hot",
    "warm": "Warm",
    "cold": "Cold",
    "avoid": "Avoid",
}

_PLATFORM_WORDS = {
    "wordpress": "wordpress",
    "wp": "wordpress",
    "wix": "wix",
    "shopify": "shopify",
    "squarespace": "squarespace",
    "weebly": "weebly",
    "custom html": "custom_html",
    "custom react": "custom_react",
}

_WEAK_SEO_RE = re.compile(r"\b(weak|poor|bad|low|terrible|issue(s)?)\s+seo\b|\bseo\s+(is\s+)?(weak|poor|bad|low)\b")
_WEAK_VISUAL_RE = re.compile(
    r"\b(weak|poor|bad|outdated|ugly)\s+(design|visual|mobile|layout|presentation|site)\b"
    r"|\b(weak|poor|bad)\s+visual\b|\blooks?\s+(outdated|old|dated)\b"
    r"|\b(?:outdated|old|ugly|weak)\s+website\b"
)
_THRESHOLD_RE = re.compile(
    r"\b(?:above|over|at least|greater than|more than|minimum of)\s+(\d{1,3})\b"
)
_TOP_N_RE = re.compile(r"\b(?:top|first|best)\s+(\d{1,3})\b|\b(\d{1,3})\s+(?:leads?|businesses?|results)\b")
_NO_WEBSITE_RE = re.compile(r"\b(?:no|without|with no|missing|absent)\s+a?\s*(?:website|url|web presence)\b")
_STRONG_OPPORTUNITY_RE = re.compile(r"\b(redesign|opportunity|opportunities)\b")
_BAND_RE = re.compile(r"\b(hot|warm|cold|avoid)\b", re.IGNORECASE)
_DETAIL_RE = re.compile(
    r"\b(tell me about|details? (?:on|about|for)|who is|what is|profile|describe)\s+(.+)$",
    re.IGNORECASE,
)
_SIMILAR_NAME_RE = re.compile(
    r"\bsimilar\s+(?:businesses?\s+(?:to|as)|to|plumbing|companies?\s+like)\s+(.+)$",
    re.IGNORECASE,
)
_SIMILAR_LIKE_RE = re.compile(r"\b(more leads? like|businesses? like|leads? like|similar to)\s+(.+)$", re.IGNORECASE)


@dataclass(frozen=True)
class RouteHints:
    """Known distinct values used to recognize entities in the question.

    Provided by the retriever from the live database so routing stays offline
    and data-driven (e.g. category "Restaurant" or city "Bangalore").
    """

    categories: tuple[str, ...] = ()
    cities: tuple[str, ...] = ()
    states: tuple[str, ...] = ()
    countries: tuple[str, ...] = ()
    platforms: tuple[str, ...] = ()
    business_names: tuple[str, ...] = ()

    @staticmethod
    def empty() -> "RouteHints":
        return RouteHints()


def route_query(query: str, hints: Optional[RouteHints] = None) -> IntentRoute:
    """Classify a natural-language question into an intent + parameters."""
    hints = hints or RouteHints.empty()
    raw = (query or "").strip()
    normalized = " ".join(raw.lower().split())
    if not normalized:
        return IntentRoute(intent=Intent.SEARCH, params={"top_n": 5}, raw_query=query or "")

    params: dict[str, Any] = {}
    _extract_top_n(normalized, params)
    _extract_priority_band(normalized, params)
    _extract_threshold(normalized, params)
    _extract_seo_signal(normalized, params)
    _extract_visual_signal(normalized, params)
    _extract_website_presence(normalized, params)
    _extract_platform(normalized, params)
    _extract_place(normalized, hints, params)
    _extract_business_name(normalized, hints, params)

    intent = _detect_intent(normalized)
    if intent is Intent.SEARCH and params:
        intent = _intent_from_params(params) or Intent.SEARCH

    if intent is Intent.SEARCH and params.get("business_name"):
        intent = Intent.DETAIL

    if intent not in {Intent.DETAIL, Intent.SIMILAR, Intent.COMPARE}:
        params.pop("business_name", None)
        params.pop("business_names", None)

    return IntentRoute(intent=intent, params=params, raw_query=query or "")


def _detect_intent(normalized: str) -> Intent:
    if re.search(r"\bsimilar\b|like this|more like \w|more (?:leads?|businesses?|companies?) like|leads? like", normalized):
        return Intent.SIMILAR
    if _DETAIL_RE.search(normalized):
        return Intent.DETAIL
    if "compare" in normalized or re.search(r"\b(vs|versus)\b", normalized):
        return Intent.COMPARE
    if "summarize" in normalized or "summary" in normalized or "overview" in normalized:
        return Intent.SUMMARIZE
    if re.search(r"\b(why|explain)\b", normalized) or "how was" in normalized:
        return Intent.EXPLAIN
    if re.search(
        r"\b(message|contact|reach out|pitch|outreach|easiest to pitch|email|call)\b",
        normalized,
    ):
        return Intent.OUTREACH
    if re.search(r"\b(top|best|rank|prioritize|highest|which .* first|strongest)\b", normalized):
        return Intent.RANK
    return Intent.SEARCH


def _intent_from_params(params: dict[str, Any]) -> Optional[Intent]:
    if params.get("top_n"):
        return Intent.RANK
    return None


def _extract_top_n(normalized: str, params: dict[str, Any]) -> None:
    match = _TOP_N_RE.search(normalized)
    if match:
        value = int(next(g for g in match.groups() if g))
        params["top_n"] = value


def _extract_priority_band(normalized: str, params: dict[str, Any]) -> None:
    for word, band in _PRIORITY_BANDS.items():
        if re.search(rf"\b{word}\b", normalized):
            params["priority"] = band
            return


def _extract_threshold(normalized: str, params: dict[str, Any]) -> None:
    match = _THRESHOLD_RE.search(normalized)
    if not match:
        return
    threshold = int(match.group(1))
    if _STRONG_OPPORTUNITY_RE.search(normalized):
        key = "opportunity_score"
    elif "seo" in normalized:
        key = "seo_score"
    elif "visual" in normalized:
        key = "visual_score"
    else:
        key = "lead_score"
    params[key] = {"min": threshold}


def _extract_seo_signal(normalized: str, params: dict[str, Any]) -> None:
    if _WEAK_SEO_RE.search(normalized):
        params["seo_score"] = {"max": 60}
    elif re.search(r"\bshows?\s+(?:a\s+)?(?:weak|poor|bad|low)\s+seo\b", normalized):
        params["seo_score"] = {"max": 60}


def _extract_visual_signal(normalized: str, params: dict[str, Any]) -> None:
    if _WEAK_VISUAL_RE.search(normalized):
        params["visual_score"] = {"max": 60}


def _extract_website_presence(normalized: str, params: dict[str, Any]) -> None:
    if _NO_WEBSITE_RE.search(normalized):
        params["website_present"] = False


def _extract_platform(normalized: str, params: dict[str, Any]) -> None:
    for word, enum_value in _PLATFORM_WORDS.items():
        if re.search(rf"\b{re.escape(word)}\b", normalized):
            params["platform"] = enum_value
            return


def _extract_place(normalized: str, hints: RouteHints, params: dict[str, Any]) -> None:
    for key, values in (
        ("category", hints.categories),
        ("city", hints.cities),
        ("state", hints.states),
        ("country", hints.countries),
    ):
        for value in values:
            lowered = str(value).strip().lower()
            if not lowered or len(lowered) < 2:
                continue
            if lowered in normalized:
                params[key] = str(value)
                break


def _extract_business_name(normalized: str, hints: RouteHints, params: dict[str, Any]) -> None:
    matched = [str(name) for name in hints.business_names if str(name).strip().lower() and str(name).strip().lower() in normalized]
    if matched:
        params["business_name"] = matched[0]
        if len(matched) > 1:
            params["business_names"] = matched[1:]
        return
    for pattern, group_index in ((_DETAIL_RE, 2), (_SIMILAR_NAME_RE, 1), (_SIMILAR_LIKE_RE, 1)):
        match = pattern.search(normalized)
        if match:
            params["business_name"] = match.group(group_index).strip().strip("?")
            return