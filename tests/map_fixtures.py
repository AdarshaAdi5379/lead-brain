"""Synthetic fixtures for the interactive map tests (no network, no DB)."""

from __future__ import annotations

from typing import Optional

from src.map.map_data import MapLead


def map_lead(
    lead_id: int,
    *,
    name: Optional[str] = None,
    category: Optional[str] = "Restaurant",
    city: Optional[str] = "Austin",
    state: Optional[str] = "TX",
    platform: Optional[str] = "WordPress",
    lat: Optional[float] = 30.2,
    lon: Optional[float] = -97.7,
    website: Optional[str] = "https://taco.com",
    lead_score: Optional[int] = 80,
    priority: Optional[str] = "Hot",
    opportunity_score: int = 90,
    has_contact: bool = True,
) -> MapLead:
    return MapLead(
        id=lead_id,
        business_name=name or f"Biz {lead_id}",
        category=category,
        city=city,
        state=state,
        platform=platform,
        latitude=lat,
        longitude=lon,
        website_url=website,
        lead_score=lead_score,
        priority_label=priority,
        opportunity_score=opportunity_score,
        has_contact=has_contact,
    )


def map_leads() -> list[MapLead]:
    """Three leads in Austin + one in Dallas, varied scores/contact."""
    return [
        map_lead(1, name="Taco Stand", lead_score=82, priority="Hot"),
        map_lead(
            2,
            name="Round Rock Cafe",
            city="Round Rock",
            lead_score=60,
            priority="Warm",
            website=None,
            has_contact=False,
        ),
        map_lead(
            3,
            name="Cold Barber",
            lead_score=35,
            priority="Cold",
            platform="Wix",
            opportunity_score=45,
        ),
        map_lead(
            4,
            name="Dallas Plumber",
            city="Dallas",
            state="TX",
            category="Plumber",
            platform="Wix",
            lead_score=70,
            priority="Warm",
        ),
    ]