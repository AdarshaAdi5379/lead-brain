from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Optional


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
    """

    owner_name: Optional[str] = None
    address: Optional[str] = None
    postal_code: Optional[str] = None
    country: Optional[str] = None
    opening_hours: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
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
    """
    merged: dict[str, object] = {}
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
    return ContactSignals(
        **{name: merged.get(name) for name in SCALAR_FIELDS},
        service_areas=list(merged.get("service_areas") or []),
        social_urls=list(merged.get("social_urls") or []),
    )
