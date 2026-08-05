from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Any, Optional, Sequence

from src.map.map_filters import valid_coordinates

# Data plumbing for the map: one lightweight query that pulls the leads which
# actually have coordinates, joined with the stored lead score and the top
# opportunity score. Reuses the ``leads`` / ``lead_scores`` /
# ``business_opportunities`` tables already populated by the pipeline -- no new
# tables, no geocoding.

_SELECT_LEADS_SQL = """
SELECT
  l.id, l.business_name, l.category, l.city, l.state, l.platform,
  l.latitude, l.longitude, l.website_url,
  l.email, l.phone, l.owner_name,
  l.contact_page_url, l.contact_form_url,
  l.facebook_url, l.linkedin_url, l.whatsapp_url,
  l.instagram_url, l.twitter_url,
  s.final_score AS lead_score,
  s.priority_label AS priority_label,
  (SELECT COALESCE(MAX(o.score), 0)
     FROM business_opportunities o WHERE o.lead_id = l.id) AS opportunity_score
FROM leads l
LEFT JOIN lead_scores s ON s.lead_id = l.id
WHERE l.latitude IS NOT NULL AND l.longitude IS NOT NULL
ORDER BY l.id
"""

_CONTACT_COLUMNS = (
    "email",
    "phone",
    "owner_name",
    "contact_page_url",
    "contact_form_url",
    "facebook_url",
    "linkedin_url",
    "whatsapp_url",
    "instagram_url",
    "twitter_url",
)


@dataclass(frozen=True)
class MapLead:
    """Minimal, geolocatable view of one lead for the map (no other engine data)."""

    id: int
    business_name: Optional[str]
    category: Optional[str]
    city: Optional[str]
    state: Optional[str]
    platform: Optional[str]
    latitude: float
    longitude: float
    website_url: Optional[str]
    lead_score: Optional[int]
    priority_label: Optional[str]
    opportunity_score: int
    has_contact: bool


def _clean(value: Any) -> Optional[str]:
    text = str(value or "").strip()
    return text or None


def _to_int(value: Any) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _has_contact(row: dict[str, Any]) -> bool:
    return any(bool(str(row.get(key) or "").strip()) for key in _CONTACT_COLUMNS)


def load_map_leads(connection: sqlite3.Connection) -> list[MapLead]:
    """Leads with stored coordinates (invalid or missing coordinates skipped)."""
    rows = [dict(row) for row in connection.execute(_SELECT_LEADS_SQL).fetchall()]
    leads: list[MapLead] = []
    for row in rows:
        latitude, longitude = row.get("latitude"), row.get("longitude")
        if not valid_coordinates(latitude, longitude):
            continue
        leads.append(
            MapLead(
                id=int(row["id"]),
                business_name=_clean(row.get("business_name")),
                category=_clean(row.get("category")),
                city=_clean(row.get("city")),
                state=_clean(row.get("state")),
                platform=_clean(row.get("platform")),
                latitude=float(latitude),
                longitude=float(longitude),
                website_url=_clean(row.get("website_url")),
                lead_score=_to_int(row.get("lead_score")),
                priority_label=_clean(row.get("priority_label")),
                opportunity_score=int(row.get("opportunity_score") or 0),
                has_contact=_has_contact(row),
            )
        )
    return leads


def option_values(leads: Sequence[MapLead]) -> dict[str, list[str]]:
    """Sorted, de-duplicated dropdown options derived from the cohort."""
    values: dict[str, list[str]] = {"categories": [], "cities": [], "states": [], "platforms": []}
    for key in values:
        seen: list[str] = []
        for lead in leads:
            value = str(getattr(lead, {"categories": "category", "cities": "city", "states": "state", "platforms": "platform"}[key]) or "").strip()
            if value and value not in seen:
                seen.append(value)
        values[key] = sorted(seen)
    return values