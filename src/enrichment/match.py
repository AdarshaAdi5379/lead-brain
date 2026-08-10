from __future__ import annotations

import re
from typing import Optional
from urllib.parse import urlparse

from src.enrichment.base import LeadContext

_STOPWORDS = frozenset(
    {
        "the", "a", "an", "and", "or", "of", "for", "to", "in", "at", "on",
        "with", "by", "from", "is", "as",
        "llc", "inc", "ltd", "corp", "corporation", "company", "co",
    }
)

# Free/webmail providers: their domains never identify a business website.
_FREE_MAIL_DOMAINS = frozenset(
    {
        "gmail.com", "googlemail.com", "yahoo.com", "ymail.com", "outlook.com",
        "hotmail.com", "live.com", "msn.com", "icloud.com", "me.com",
        "aol.com", "protonmail.com", "proton.me", "zoho.com", "gmx.com",
        "mail.com", "yandex.com", "qq.com", "163.com", "126.com", "sina.com",
        "comcast.net", "cox.net", "verizon.net", "att.net", "earthlink.net",
        "bellsouth.net", "charter.net", "roadrunner.com",
    }
)

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_PHONE_DIGITS_RE = re.compile(r"\d+")


def _tokens(text: Optional[str]) -> list[str]:
    found = _TOKEN_RE.findall((text or "").lower())
    return [token for token in found if token not in _STOPWORDS and len(token) > 1]


def _title_has_name_sequence(name_tokens: list[str], title_tokens: list[str]) -> bool:
    """Whether the business name appears as a contiguous title token run.

    Much stronger than scattered single-token hits: "Radiant Plumbing" in a
    title is decisive, while a title that merely contains the industry word
    "Plumbing" is not.
    """
    width = len(name_tokens)
    if width <= 1:
        return False
    return any(
        title_tokens[index : index + width] == name_tokens
        for index in range(len(title_tokens) - width + 1)
    )


def brand_component(name: Optional[str], title: str, text: str) -> float:
    """Strength of the business-name signal on the candidate page (0 max 0.55).

    Conservative by design: the full name as a contiguous title run is the
    strongest evidence; partial token overlap (e.g. only the industry word
    of a multi-word name) never reaches it. Single-token names are only
    accepted when the token appears in both the title and the body.
    """
    name_tokens = _tokens(name)
    if not name_tokens:
        return 0.0
    title_tokens = _tokens(title)
    body_tokens = set(_tokens(text))
    title_containment = sum(1 for token in name_tokens if token in title_tokens) / len(name_tokens)
    body_containment = sum(1 for token in name_tokens if token in body_tokens) / len(name_tokens)

    if _title_has_name_sequence(name_tokens, title_tokens):
        return 0.55
    if title_containment >= 0.75:
        return 0.55
    if len(name_tokens) >= 2:
        if body_containment >= 0.75:
            return 0.55
        if title_containment >= 0.5 or body_containment >= 0.4:
            return 0.30
        return 0.0
    if body_containment >= 1.0 and title_containment >= 1.0:
        return 0.55
    return 0.0


def _as_digit_run(value: Optional[str]) -> str:
    return "".join(_PHONE_DIGITS_RE.findall(value or ""))


def phone_component(lead_phone: Optional[str], text: str) -> float:
    """Phone-number match between the lead and the candidate page (max 0.35)."""
    digits = _as_digit_run(lead_phone)
    if len(digits) < 7:
        return 0.0
    return 0.35 if digits in _as_digit_run(text) else 0.0


def _bare_host(url: str) -> str:
    host = urlparse(url).netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    return host.split(":")[0]


def email_domain_component(candidate_url: str, lead_email: Optional[str]) -> float:
    """Email-domain match between the lead and the candidate host (max 0.35)."""
    if not lead_email:
        return 0.0
    domain = (lead_email.strip().rsplit("@", 1)[-1] if "@" in lead_email else "").lower()
    if not domain:
        return 0.0
    host = _bare_host(candidate_url)
    return 0.35 if host and (host == domain or host.endswith("." + domain)) else 0.0


def location_component(city: Optional[str], state: Optional[str], text: str) -> float:
    """City and/or state co-occurrence on the candidate page (max 0.15)."""
    tokens = set(_tokens(text))
    city_tokens = _tokens(city)
    state_tokens = _tokens(state)
    city_ok = bool(city_tokens) and all(token in tokens for token in city_tokens)
    state_ok = bool(state_tokens) and all(token in tokens for token in state_tokens)
    if city_ok and state_ok:
        return 0.15
    if city_ok:
        return 0.08
    return 0.0


def category_component(category: Optional[str], text: str) -> float:
    """Category keyword presence on the candidate page (max 0.05)."""
    tokens = set(_tokens(text))
    category_tokens = _tokens(category)
    if category_tokens and all(token in tokens for token in category_tokens):
        return 0.05
    return 0.0


def score_candidate(candidate_url: str, *, title: str, text: str, lead: LeadContext) -> tuple[float, dict[str, float]]:
    """Deterministic confidence score (0-1) for a candidate website.

    Independent evidence weights sum against a 1.0 cap. A page with no brand
    signal scores 0 regardless of anything else (no phone/address-only
    acceptance), so directory-style or unrelated pages never pass.
    """
    signals = {
        "brand": brand_component(lead.business_name, title, text),
        "phone": phone_component(lead.phone, text),
        "email_domain": email_domain_component(candidate_url, lead.email),
        "location": location_component(lead.city, lead.state, f"{title} {text}"),
        "category": category_component(lead.category, f"{title} {text}"),
    }
    if signals["brand"] <= 0.0:
        return 0.0, signals
    return min(1.0, sum(signals.values())), signals


def email_domain_candidate(email: Optional[str]) -> Optional[str]:
    """Build a candidate website from a company email's private domain.

    Returns None for missing emails, free/webmail providers, malformed
    addresses and domains that fail URL normalization.
    """
    if not email or "@" not in email:
        return None
    domain = email.strip().rsplit("@", 1)[-1].strip().lower().rstrip(".")
    if not domain or domain in _FREE_MAIL_DOMAINS:
        return None
    from src.enrichment.normalizer import clean_candidate_url

    return clean_candidate_url(f"https://{domain}")