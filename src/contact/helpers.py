from __future__ import annotations

import re
from typing import Optional
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

from src.llm_extraction import _sanitize_email, _sanitize_phone

# Query parameters that are pure tracking noise; dropped from stored URLs.
_TRACKING_PARAMS = {"fbclid", "gclid", "igshid", "mc_cid", "mc_eid", "ref", "utm_source",
                    "utm_medium", "utm_campaign", "utm_term", "utm_content"}

_CONTACT_PAGE_LABELS = {"contact", "contacts", "contactus", "contact-us", "get-in-touch"}

_WHITESPACE_RE = re.compile(r"\s+")


def clean_text(value: object) -> Optional[str]:
    """Trim and collapse whitespace; None for empty strings."""
    if value is None:
        return None
    text = _WHITESPACE_RE.sub(" ", str(value)).strip()
    return text or None


def normalize_absolute_url(raw: Optional[str], base: Optional[str] = None) -> Optional[str]:
    """Resolve a raw href/value against a base URL and validate it.

    Only http/https URLs survive; javascript:, mailto:, tel:, data: and empty
    values are rejected, fragments and tracking parameters are dropped.
    """
    text = clean_text(raw)
    if not text:
        return None
    joined = urljoin(base or "", text)
    parsed = urlparse(joined)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return None
    query = _drop_tracking(parsed.query)
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", query, ""))


def _drop_tracking(query: str) -> str:
    if not query:
        return ""
    kept = [(k, v) for k, v in parse_qsl(query, keep_blank_values=True) if k.lower() not in _TRACKING_PARAMS]
    return urlencode(kept) if kept else ""


def normalize_phone(value: object) -> Optional[str]:
    """Reuse the pipeline's existing phone sanitizer."""
    return _sanitize_phone(value)


def normalize_email(value: object) -> Optional[str]:
    """Reuse the pipeline's existing email sanitizer."""
    return _sanitize_email(value)


def google_maps_url(latitude: Optional[float], longitude: Optional[float]) -> Optional[str]:
    """Locally-built Google Maps search URL from coordinates (no API needed)."""
    try:
        lat = float(latitude)
        lon = float(longitude)
    except (TypeError, ValueError):
        return None
    if not (-90.0 <= lat <= 90.0) or not (-180.0 <= lon <= 180.0):
        return None
    return f"https://www.google.com/maps/search/?api=1&query={lat:.6f},{lon:.6f}"


def is_contact_page(page_label: Optional[str], page_url: Optional[str]) -> bool:
    """Whether a page looks like a contact page (label or URL path heuristic)."""
    label = (page_label or "").strip().lower()
    if label in _CONTACT_PAGE_LABELS:
        return True
    url = (page_url or "").lower()
    path = urlparse(url).path
    return "contact" in path and path.rstrip("/").split("/")[-1] != ""


def page_priority_key(page_label: Optional[str]) -> int:
    """Ordering used when merging per-page signals into a lead-level set."""
    label = (page_label or "").strip().lower()
    if label == "home":
        return 0
    if label in _CONTACT_PAGE_LABELS:
        return 1
    if label in {"about", "aboutus", "about-us", "who-we-are", "team"}:
        return 2
    return 9
