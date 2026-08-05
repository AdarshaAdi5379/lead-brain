from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Optional

from src.contact.sources import ContactCandidate


# Scalar fields captured by the contact intelligence engine, in merge order.
SCALAR_FIELDS = (
    "owner_name",
    "address",
    "postal_code",
    "country",
    "opening_hours",
    "phone",
    "email",
    "facebook_url",
    "instagram_url",
    "linkedin_url",
    "twitter_url",
    "youtube_url",
    "whatsapp_url",
    "contact_page_url",
    "contact_form_url",
    "google_maps_url",
)

LIST_FIELDS = ("service_areas", "social_urls")


@dataclass(frozen=True)
class ContactSignals:
    """Structured contact facts extracted deterministically from page HTML.

    All fields are optional: missing facts stay None/empty so storage always
    keeps a single authoritative value per field (never invented, never
    guessed). ``social_urls`` additionally lists every social profile URL
    found so the scoring engine's existing social-link signal can fire.
    ``email_candidates``/``phone_candidates`` track every deterministic value
    and its source so a lead-level best pick can be made across pages.
    """

    owner_name: Optional[str] = None
    address: Optional[str] = None
    postal_code: Optional[str] = None
    country: Optional[str] = None
    opening_hours: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    phone_source: Optional[str] = None
    email_source: Optional[str] = None
    phone_confidence: Optional[float] = None
    email_confidence: Optional[float] = None
    email_candidates: list[ContactCandidate] = field(default_factory=list)
    phone_candidates: list[ContactCandidate] = field(default_factory=list)
    facebook_url: Optional[str] = None
    instagram_url: Optional[str] = None
    linkedin_url: Optional[str] = None
    twitter_url: Optional[str] = None
    youtube_url: Optional[str] = None
    whatsapp_url: Optional[str] = None
    contact_page_url: Optional[str] = None
    contact_form_url: Optional[str] = None
    google_maps_url: Optional[str] = None
    service_areas: list[str] = field(default_factory=list)
    social_urls: list[str] = field(default_factory=list)

    def non_empty_fields(self) -> dict[str, object]:
        """First-seen, non-empty field values for debugging/inspection."""
        values: dict[str, object] = {}
        for name in SCALAR_FIELDS:
            value = getattr(self, name)
            if value:
                values[name] = value
        for name in LIST_FIELDS:
            value = getattr(self, name)
            if value:
                values[name] = list(value)
        return values


def merge_contact_signals(signals: Iterable[ContactSignals]) -> ContactSignals:
    """Merge multiple page-level signal sets into one lead-level set.

    First non-empty value wins for scalars (never overwriting a valid value
    with an empty one); lists are unioned preserving first-seen order.
    Candidate lists are unioned so the caller can re-pick the best value
    across all pages after merging.
    """
    merged: dict[str, object] = {}
    candidate_lists: dict[str, list[ContactCandidate]] = {
        "email_candidates": [],
        "phone_candidates": [],
    }
    for signal in signals:
        if signal is None:
            continue
        for name in SCALAR_FIELDS:
            value = getattr(signal, name)
            if value and not merged.get(name):
                merged[name] = value
        for name in LIST_FIELDS:
            existing = merged.setdefault(name, [])
            assert isinstance(existing, list)
            for item in getattr(signal, name):
                if item and item not in existing:
                    existing.append(item)
        for name, bucket in candidate_lists.items():
            seen = {(c.value.lower(), c.source) for c in bucket}
            for candidate in getattr(signal, name):
                key = (candidate.value.lower(), candidate.source)
                if key not in seen:
                    bucket.append(candidate)
                    seen.add(key)
    email_candidates = candidate_lists["email_candidates"]
    phone_candidates = candidate_lists["phone_candidates"]
    return ContactSignals(
        **{name: merged.get(name) for name in SCALAR_FIELDS},
        service_areas=list(merged.get("service_areas") or []),
        social_urls=list(merged.get("social_urls") or []),
        email_candidates=email_candidates,
        phone_candidates=phone_candidates,
        email_source=_source_for(merged.get("email"), email_candidates),
        email_confidence=_confidence_for(merged.get("email"), email_candidates),
        phone_source=_source_for(merged.get("phone"), phone_candidates),
        phone_confidence=_confidence_for(merged.get("phone"), phone_candidates),
    )


def _source_for(value: object, candidates: list[ContactCandidate]) -> Optional[str]:
    if value is None:
        return None
    needle = str(value).lower()
    for candidate in candidates:
        if candidate.value.lower() == needle:
            return candidate.source
    return None


def _confidence_for(value: object, candidates: list[ContactCandidate]) -> Optional[float]:
    if value is None:
        return None
    needle = str(value).lower()
    for candidate in candidates:
        if candidate.value.lower() == needle:
            return candidate.confidence
    return None
