from __future__ import annotations

from typing import Any, Mapping

# Presentation helpers for the stored contact intelligence (dashboard detail
# view). Pure functions over plain mappings — no Streamlit, no network, no
# LLM — so the grouping rules are unit-testable and reused by the dashboard.

CONTACT_FIELDS = (
    "owner_name",
    "address",
    "postal_code",
    "country",
    "opening_hours",
    "phone",
    "email",
    "website_url",
    "facebook_url",
    "instagram_url",
    "linkedin_url",
    "twitter_url",
    "youtube_url",
    "whatsapp_url",
    "contact_page_url",
    "contact_form_url",
    "google_maps_url",
    "service_areas",
)

_SOCIAL_LABELS = (
    ("facebook_url", "Facebook"),
    ("instagram_url", "Instagram"),
    ("linkedin_url", "LinkedIn"),
    ("twitter_url", "Twitter/X"),
    ("youtube_url", "YouTube"),
    ("whatsapp_url", "WhatsApp"),
)

_GROUPS = (
    ("Business", ("owner_name",)),
    ("Contact", ("phone", "email")),
    (
        "Location",
        ("address", "postal_code", "country", "google_maps_url"),
    ),
    ("Website & Forms", ("website_url", "contact_page_url", "contact_form_url")),
    ("Social links", tuple(url for url, _ in _SOCIAL_LABELS)),
    ("Opening hours", ("opening_hours",)),
    ("Service areas", ("service_areas",)),
)


def lead_contact_dict(contact: Mapping[str, Any]) -> dict[str, Any]:
    """Non-empty contact facts from a mapping (LeadRow, DB row, intel dict)."""
    return {
        name: value
        for name in CONTACT_FIELDS
        if (value := _non_empty(contact.get(name)))
    }


def group_contact_facts(contact: Mapping[str, Any]) -> list[tuple[str, str, str]]:
    """Grouped ``(group, label, value)`` rows, empty/NULL values omitted.

    Deterministic order follows ``_GROUPS``; only groups with at least one
    fact are emitted. ``service_areas`` renders as a comma-joined string.
    """
    facts = lead_contact_dict(contact)
    rows: list[tuple[str, str, str]] = []
    for group, field_names in _GROUPS:
        group_rows: list[tuple[str, str, str]] = []
        for name in field_names:
            value = facts.get(name)
            if not value:
                continue
            if name == "service_areas":
                value = ", ".join(
                    str(item) for item in facts[name] if str(item).strip()
                )
                if not value:
                    continue
                label = "Service areas"
            else:
                label = _label_for(name)
            group_rows.append((group, label, str(value)))
        rows.extend(group_rows)
    return rows


def _label_for(name: str) -> str:
    for url, label in _SOCIAL_LABELS:
        if name == url:
            return label
    return {
        "owner_name": "Owner",
        "address": "Address",
        "postal_code": "Postal code",
        "country": "Country",
        "opening_hours": "Opening hours",
        "phone": "Phone",
        "email": "Email",
        "website_url": "Website",
        "contact_page_url": "Contact page",
        "contact_form_url": "Contact form",
        "google_maps_url": "Google Maps",
    }[name]


def _non_empty(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        return [item for item in value if str(item).strip()] or None
    return str(value).strip() or None
