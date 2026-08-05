from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse

JSON_LD = "json_ld"
MAILTO = "mailto"
TEL = "tel"
SCHEMA = "schema"
VISIBLE_TEXT = "visible_text"
LLM = "llm"
OSM = "osm"
CSV = "csv"

_SOURCE_RANKS: dict[str, int] = {
    JSON_LD: 100,
    MAILTO: 90,
    TEL: 90,
    SCHEMA: 85,
    VISIBLE_TEXT: 70,
    LLM: 60,
    OSM: 40,
    CSV: 30,
}

_SPECIAL_PREFIXES: dict[str, int] = {
    "hello": 1,
    "contact": 1,
    "enquiries": 1,
    "enquiry": 1,
    "inquiries": 1,
    "inquiry": 1,
    "sales": 2,
    "support": 2,
    "info": 3,
}


def source_rank(source: Optional[str]) -> int:
    return _SOURCE_RANKS.get(source, 0)


@dataclass(frozen=True)
class ContactCandidate:
    value: str
    source: str
    confidence: Optional[float] = None
    order: int = 0


def _business_domain(email: str, website_url: Optional[str]) -> bool:
    if not website_url:
        return False
    try:
        domain = urlparse(website_url).netloc.lower()
    except ValueError:
        return False
    if not domain:
        return False
    if domain.startswith("www."):
        domain = domain[4:]
    local, at, host = email.lower().partition("@")
    if not at:
        return False
    if host.startswith("www."):
        host = host[4:]
    return host == domain


def _email_rank(email: str, website_url: Optional[str]) -> tuple[int, int]:
    business = 0 if _business_domain(email, website_url) else 1
    local = email.partition("@")[0].strip(".-").lower()
    return (business, _SPECIAL_PREFIXES.get(local, 4))


def _best_by_value(candidates: list[ContactCandidate]) -> list[ContactCandidate]:
    """One candidate per value; ties keep the strongest source, then first-seen."""
    best_by_value: dict[str, ContactCandidate] = {}
    for candidate in candidates:
        key = candidate.value.lower()
        existing = best_by_value.get(key)
        if existing is None or (source_rank(candidate.source), -candidate.order) > (
            source_rank(existing.source),
            -existing.order,
        ):
            best_by_value[key] = candidate
    return list(best_by_value.values())


def pick_best_email(candidates: list[ContactCandidate], website_url: Optional[str] = None) -> Optional[ContactCandidate]:
    unique = _best_by_value(candidates)
    if not unique:
        return None
    return min(unique, key=lambda c: (*_email_rank(c.value, website_url), c.order))


def pick_best_phone(candidates: list[ContactCandidate]) -> Optional[ContactCandidate]:
    unique = _best_by_value(candidates)
    if not unique:
        return None
    return min(unique, key=lambda c: (0 if c.value.startswith("+") else 1, c.order))


def better_contact(
    existing_value: Optional[str],
    existing_source: Optional[str],
    existing_confidence: Optional[float],
    incoming_value: Optional[str],
    incoming_source: Optional[str],
    incoming_confidence: Optional[float],
) -> tuple[Optional[str], Optional[str], Optional[float]]:
    if incoming_value is None:
        return existing_value, existing_source, existing_confidence
    if existing_value is None:
        return incoming_value, incoming_source, incoming_confidence

    existing_key = existing_value.lower() if isinstance(existing_value, str) else existing_value
    incoming_key = incoming_value.lower() if isinstance(incoming_value, str) else incoming_value
    if existing_key == incoming_key:
        existing_rank = source_rank(existing_source)
        incoming_rank = source_rank(incoming_source)
        if incoming_rank > existing_rank:
            return incoming_value, incoming_source, incoming_confidence
        return existing_value, existing_source, existing_confidence

    existing_rank = source_rank(existing_source)
    incoming_rank = source_rank(incoming_source)
    if incoming_rank > existing_rank:
        return incoming_value, incoming_source, incoming_confidence
    if incoming_rank < existing_rank:
        return existing_value, existing_source, existing_confidence
    if (incoming_confidence or 0) > (existing_confidence or 0):
        return incoming_value, incoming_source, incoming_confidence
    return existing_value, existing_source, existing_confidence


def pick_across_sources(*refs: tuple[Optional[str], Optional[str], Optional[float]]) -> tuple[Optional[str], Optional[str], Optional[float]]:
    best_value, best_source, best_confidence = None, None, None
    for value, source, confidence in refs:
        best_value, best_source, best_confidence = better_contact(
            best_value, best_source, best_confidence, value, source, confidence
        )
    return best_value, best_source, best_confidence
