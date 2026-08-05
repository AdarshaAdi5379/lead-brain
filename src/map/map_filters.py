from __future__ import annotations

from typing import Any, Optional, Sequence

from src.scoring.config import ScoringConfig

# Pure, deterministic map filters (no network, no DB access).
#
# Reuses the project's canonical score bands from the scoring engine so the
# marker groups (Hot/Warm/Cold/Avoid) never drift from the lead priority
# labels that the dashboard already shows.

_DEFAULT_PRIORITY_BANDS: tuple[tuple[int, str], ...] = tuple(
    ScoringConfig().priority_bands
)


def valid_coordinates(latitude: Any, longitude: Any) -> bool:
    """True when both values parse as floats inside the valid lat/lng ranges."""
    try:
        lat = float(latitude)
        lon = float(longitude)
    except (TypeError, ValueError):
        return False
    return -90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0


def score_group(
    score: Any, bands: Sequence[tuple[int, str]] = _DEFAULT_PRIORITY_BANDS
) -> str:
    """Map a lead score onto the canonical priority group (Hot/Warm/Cold/Avoid)."""
    try:
        score = int(score)
    except (TypeError, ValueError):
        return "Avoid"
    for threshold, label in bands:
        if score >= int(threshold):
            return str(label)
    return "Avoid"


def filter_leads(
    leads: Sequence[Any],
    *,
    min_lead_score: int = 0,
    priority_labels: Optional[Sequence[str]] = None,
    categories: Optional[Sequence[str]] = None,
    cities: Optional[Sequence[str]] = None,
    states: Optional[Sequence[str]] = None,
    platforms: Optional[Sequence[str]] = None,
    has_website: Optional[bool] = None,
    has_contact: Optional[bool] = None,
    only_with_coordinates: bool = True,
) -> list[Any]:
    """Filter map leads by the dashboard-style criteria.

    ``None``-valued criteria are ignored. ``None`` has_website/has_contact mean
    "any". Leads may be any object exposing id/business_name/category/city/
    state/platform/latitude/longitude/website_url/lead_score/priority_label/
    has_contact (i.e. ``MapLead``).
    """
    allowed_priority = {str(p) for p in priority_labels} if priority_labels else None
    allowed_categories = {str(c) for c in categories} if categories else None
    allowed_cities = {str(c) for c in cities} if cities else None
    allowed_states = {str(s) for s in states} if states else None
    allowed_platforms = {str(p) for p in platforms} if platforms else None

    matched: list[Any] = []
    for lead in leads:
        latitude = getattr(lead, "latitude", None)
        longitude = getattr(lead, "longitude", None)
        if only_with_coordinates and not valid_coordinates(latitude, longitude):
            continue

        score = getattr(lead, "lead_score", None)
        try:
            lead_score = int(score)
        except (TypeError, ValueError):
            lead_score = 0
        if lead_score < int(min_lead_score):
            continue

        if (
            allowed_priority is not None
            and str(getattr(lead, "priority_label", "") or "") not in allowed_priority
        ):
            continue
        if (
            allowed_categories is not None
            and str(getattr(lead, "category", "") or "") not in allowed_categories
        ):
            continue
        if allowed_cities is not None and str(getattr(lead, "city", "") or "") not in allowed_cities:
            continue
        if allowed_states is not None and str(getattr(lead, "state", "") or "") not in allowed_states:
            continue
        if allowed_platforms is not None and str(getattr(lead, "platform", "") or "") not in allowed_platforms:
            continue

        if has_website is not None and bool(getattr(lead, "website_url", None)) != bool(has_website):
            continue
        if has_contact is not None and bool(getattr(lead, "has_contact", False)) != bool(has_contact):
            continue
        matched.append(lead)
    return matched