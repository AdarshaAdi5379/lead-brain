from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from typing import Optional

from src.storage.normalization import normalize_url_for_dedupe
from urllib.parse import quote


@dataclass(frozen=True)
class LeadUpsert:
    website_url: Optional[str]
    dedupe_key: Optional[str] = None
    business_name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    platform: Optional[str] = None
    complexity: Optional[str] = None
    load_speed: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    category: Optional[str] = None
    score: Optional[int] = None
    priority: Optional[str] = None
    extraction_success: bool = False
    last_error: Optional[str] = None
    run_id: Optional[int] = None
    source: Optional[str] = None
    osm_id: Optional[str] = None
    osm_type: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    address: Optional[str] = None
    opening_hours: Optional[str] = None
    country: Optional[str] = None
    owner_name: Optional[str] = None
    postal_code: Optional[str] = None
    facebook_url: Optional[str] = None
    instagram_url: Optional[str] = None
    linkedin_url: Optional[str] = None
    twitter_url: Optional[str] = None
    youtube_url: Optional[str] = None
    whatsapp_url: Optional[str] = None
    contact_page_url: Optional[str] = None
    contact_form_url: Optional[str] = None
    google_maps_url: Optional[str] = None
    service_areas: Optional[list[str]] = None


UPSERT_SQL = """
INSERT INTO leads (
  run_id,
  business_name,
  phone,
  email,
  website_url,
  website_url_normalized,
  platform,
  complexity,
  load_speed,
  city,
  state,
  category,
  score,
  priority,
  extraction_success,
  extracted_at,
  last_error,
  source,
  osm_id,
  osm_type,
  latitude,
  longitude,
  address,
  opening_hours,
  country,
  owner_name,
  postal_code,
  facebook_url,
  instagram_url,
  linkedin_url,
  twitter_url,
  youtube_url,
  whatsapp_url,
  contact_page_url,
  contact_form_url,
  google_maps_url,
  service_areas_json
)
VALUES (
  :run_id,
  :business_name,
  :phone,
  :email,
  :website_url,
  :website_url_normalized,
  :platform,
  :complexity,
  :load_speed,
  :city,
  :state,
  :category,
  :score,
  :priority,
  :extraction_success,
  datetime('now'),
  :last_error,
  :source,
  :osm_id,
  :osm_type,
  :latitude,
  :longitude,
  :address,
  :opening_hours,
  :country,
  :owner_name,
  :postal_code,
  :facebook_url,
  :instagram_url,
  :linkedin_url,
  :twitter_url,
  :youtube_url,
  :whatsapp_url,
  :contact_page_url,
  :contact_form_url,
  :google_maps_url,
  :service_areas_json
)
ON CONFLICT(website_url_normalized) DO UPDATE SET
  run_id = excluded.run_id,
  business_name = excluded.business_name,
  phone = excluded.phone,
  email = excluded.email,
  website_url = excluded.website_url,
  platform = excluded.platform,
  complexity = excluded.complexity,
  load_speed = excluded.load_speed,
  city = excluded.city,
  state = excluded.state,
  category = excluded.category,
  score = excluded.score,
  priority = excluded.priority,
  extraction_success = excluded.extraction_success,
  extracted_at = datetime('now'),
  last_error = excluded.last_error,
  source = excluded.source,
  osm_id = excluded.osm_id,
  osm_type = excluded.osm_type,
  latitude = excluded.latitude,
  longitude = excluded.longitude,
  address = excluded.address,
  opening_hours = excluded.opening_hours,
  country = excluded.country,
  owner_name = excluded.owner_name,
  postal_code = excluded.postal_code,
  facebook_url = excluded.facebook_url,
  instagram_url = excluded.instagram_url,
  linkedin_url = excluded.linkedin_url,
  twitter_url = excluded.twitter_url,
  youtube_url = excluded.youtube_url,
  whatsapp_url = excluded.whatsapp_url,
  contact_page_url = excluded.contact_page_url,
  contact_form_url = excluded.contact_form_url,
  google_maps_url = excluded.google_maps_url,
  service_areas_json = excluded.service_areas_json;
"""


def _clean_key_part(value: Optional[str]) -> str:
    return (value or "").strip().lower()


def _business_dedupe_key(
    *,
    business_name: Optional[str],
    city: Optional[str],
    state: Optional[str],
    category: Optional[str],
) -> str:
    """
    Stable dedupe key for leads with no website URL.

    Format intentionally isn't a real URL; it's just a unique identifier.
    """

    name = _clean_key_part(business_name)
    if not name:
        return ""
    city_part = _clean_key_part(city)
    state_part = _clean_key_part(state)
    category_part = _clean_key_part(category)

    # Quote to keep the key safe/stable even with punctuation.
    return "biz://" + "|".join(
        [
            quote(name, safe=""),
            quote(city_part, safe=""),
            quote(state_part, safe=""),
            quote(category_part, safe=""),
        ]
    )


def upsert_lead(connection: sqlite3.Connection, lead: LeadUpsert) -> str:
    website_url_normalized = (lead.dedupe_key or "").strip()
    if not website_url_normalized:
        website_url_normalized = normalize_url_for_dedupe(lead.website_url)
    if not website_url_normalized:
        website_url_normalized = _business_dedupe_key(
            business_name=lead.business_name,
            city=lead.city,
            state=lead.state,
            category=lead.category,
        )
    if not website_url_normalized:
        raise ValueError(
            "Cannot upsert lead without a website URL unless business_name is present "
            "(used to create a dedupe key)."
        )

    if lead.run_id is not None:
        run_exists = connection.execute(
            "SELECT 1 FROM scraping_runs WHERE run_id = ? LIMIT 1", (lead.run_id,)
        ).fetchone()
        if run_exists is None:
            raise ValueError(
                f"run_id {lead.run_id} does not exist in scraping_runs; create the run first"
            )

    connection.execute(
        UPSERT_SQL,
        {
            "run_id": lead.run_id,
            "business_name": lead.business_name,
            "phone": lead.phone,
            "email": lead.email,
            "website_url": lead.website_url,
            "website_url_normalized": website_url_normalized,
            "platform": lead.platform,
            "complexity": lead.complexity,
            "load_speed": lead.load_speed,
            "city": lead.city,
            "state": lead.state,
            "category": lead.category,
            "score": lead.score,
            "priority": lead.priority,
            "extraction_success": 1 if lead.extraction_success else 0,
            "last_error": lead.last_error,
            "source": lead.source,
            "osm_id": lead.osm_id,
            "osm_type": lead.osm_type,
            "latitude": lead.latitude,
            "longitude": lead.longitude,
            "address": lead.address,
            "opening_hours": lead.opening_hours,
            "country": lead.country,
            "owner_name": lead.owner_name,
            "postal_code": lead.postal_code,
            "facebook_url": lead.facebook_url,
            "instagram_url": lead.instagram_url,
            "linkedin_url": lead.linkedin_url,
            "twitter_url": lead.twitter_url,
            "youtube_url": lead.youtube_url,
            "whatsapp_url": lead.whatsapp_url,
            "contact_page_url": lead.contact_page_url,
            "contact_form_url": lead.contact_form_url,
            "google_maps_url": lead.google_maps_url,
            "service_areas_json": json.dumps(lead.service_areas or []),
        },
    )
    connection.commit()
    return website_url_normalized


def update_crm_fields(
    connection: sqlite3.Connection,
    lead_id: int,
    *,
    status: Optional[str] = None,
    notes: Optional[str] = None,
    last_contacted: Optional[str] = None,
    next_follow_up: Optional[str] = None,
    assigned_to: Optional[str] = None,
    best_contact_method: Optional[str] = None,
) -> int:
    """Write the editable CRM fields back to a lead (None values are skipped).

    Used by the Excel CRM sync so manual workbook edits survive in SQLite too.
    Never raises on missing leads; parameterized, so no injection surface.
    Returns the number of rows actually updated (0 for a missing lead).
    """
    fields = {
        "status": status,
        "notes": notes,
        "last_contacted": last_contacted,
        "next_follow_up": next_follow_up,
        "assigned_to": assigned_to,
        "best_contact_method": best_contact_method,
    }
    assignments = [f"{column} = ?" for column, value in fields.items() if value is not None]
    if not assignments:
        return 0
    values = [fields[column] for column in fields if fields[column] is not None]
    cursor = connection.execute(
        f"UPDATE leads SET {', '.join(assignments)} WHERE id = ?",
        (*values, int(lead_id)),
    )
    connection.commit()
    return cursor.rowcount
