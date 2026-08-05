from __future__ import annotations

import re
from typing import Iterable, Optional

from bs4 import BeautifulSoup

from src.contact.helpers import normalize_email, normalize_phone
from src.contact.jsonld import extract_jsonld
from src.contact.microdata import extract_microdata
from src.contact.sources import (
    JSON_LD,
    MAILTO,
    SCHEMA,
    TEL,
    VISIBLE_TEXT,
    ContactCandidate,
)

EMAIL_RE = re.compile(r"\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b")

# Conservative phone-looking token: an optional leading +, at least one digit,
# then a short run of digits and separators. Shorter than _PHONE_RE's floor so
# substrings spanning markup are still caught; _plausible_phone applies strict
# digit-count and date guards before a candidate is accepted.
PHONE_TOKEN_RE = re.compile(r"(?<!\w)\+?[0-9][0-9 ().\-]{5,17}(?!\w)")

_YEAR_RANGE_RE = re.compile(r"^[12]\d{3}\s*-\s*[12]\d{3}$")
_DATE_RE = re.compile(r"^\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4}$")

# Tags whose contents (scripts, styles, templates) are not visible text.
_NOISE_TAGS = ("script", "style", "noscript", "svg", "template", "iframe")


def _plausible_phone(token: str) -> bool:
    stripped = token.strip()
    if _YEAR_RANGE_RE.match(stripped) or _DATE_RE.match(stripped):
        return False
    digits = sum(char.isdigit() for char in stripped)
    return 7 <= digits <= 15


def _as_list(value: object) -> list[object]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _dedupe(candidates: list[ContactCandidate]) -> list[ContactCandidate]:
    seen: set[str] = set()
    unique: list[ContactCandidate] = []
    for candidate in candidates:
        key = candidate.value.lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(candidate)
    return unique


def _mailto_values(soup: BeautifulSoup, prefix: str) -> list[str]:
    values: list[str] = []
    for tag in soup.find_all("a", href=True):
        href = str(tag["href"]).strip()
        lowered = href.lower()
        if not lowered.startswith(prefix):
            continue
        raw = href[len(prefix):].partition("?")[0]
        for chunk in raw.split(","):
            chunk = chunk.strip()
            if chunk and chunk not in values:
                values.append(chunk)
    return values


def _visible_text(soup: BeautifulSoup) -> str:
    for tag in soup(_NOISE_TAGS):
        tag.decompose()
    return soup.get_text(" ")


def extract_email_candidates(html: str) -> list[ContactCandidate]:
    """Deterministic email candidates from one page's raw HTML.

    Candidates are ordered by source rank (JSON-LD first) and deduplicated by
    value, so the strongest source is always the first candidate for a value.
    """
    if not html:
        return []
    soup = BeautifulSoup(html, "html.parser")
    candidates: list[ContactCandidate] = []
    order = 0

    structured = extract_jsonld(html)
    for raw in _as_list(structured.get("email")):
        value = normalize_email(raw)
        if value:
            candidates.append(ContactCandidate(value, JSON_LD, order=order))
            order += 1

    for raw in _mailto_values(soup, "mailto:"):
        value = normalize_email(raw)
        if value:
            candidates.append(ContactCandidate(value, MAILTO, order=order))
            order += 1

    for raw in extract_microdata(soup).get("email", []):
        value = normalize_email(raw)
        if value:
            candidates.append(ContactCandidate(value, SCHEMA, order=order))
            order += 1

    visible = _visible_text(soup)
    for match in EMAIL_RE.findall(visible):
        value = normalize_email(match)
        if value:
            candidates.append(ContactCandidate(value, VISIBLE_TEXT, order=order))
            order += 1

    return _dedupe(candidates)


def extract_phone_candidates(html: str) -> list[ContactCandidate]:
    """Deterministic phone candidates from one page's raw HTML."""
    if not html:
        return []
    soup = BeautifulSoup(html, "html.parser")
    candidates: list[ContactCandidate] = []
    order = 0

    structured = extract_jsonld(html)
    for raw in _as_list(structured.get("telephone")):
        value = normalize_phone(raw)
        if value:
            candidates.append(ContactCandidate(value, JSON_LD, order=order))
            order += 1

    for raw in _mailto_values(soup, "tel:"):
        value = normalize_phone(raw)
        if value:
            candidates.append(ContactCandidate(value, TEL, order=order))
            order += 1

    for raw in extract_microdata(soup).get("telephone", []):
        value = normalize_phone(raw)
        if value:
            candidates.append(ContactCandidate(value, SCHEMA, order=order))
            order += 1

    visible = _visible_text(soup)
    for match in PHONE_TOKEN_RE.findall(visible):
        if not _plausible_phone(match):
            continue
        value = normalize_phone(match)
        if value:
            candidates.append(ContactCandidate(value, VISIBLE_TEXT, order=order))
            order += 1

    return _dedupe(candidates)


def iter_candidates(html: str) -> Iterable[ContactCandidate]:
    """All email and phone candidates, email candidates first."""
    return [*extract_email_candidates(html), *extract_phone_candidates(html)]