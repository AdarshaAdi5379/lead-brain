from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, replace
from typing import Optional

from src.contact.sources import better_contact
from src.storage.normalization import normalize_url_for_dedupe
from urllib.parse import quote


@dataclass(frozen=True)
class LeadUpsert:
    website_url: Optional[str]
    dedupe_key: Optional[str] = None
    business_name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    phone_source: Optional[str] = None
    email_source: Optional[str] = None
    phone_confidence: Optional[float] = None
    email_confidence: Optional[float] = None
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
    enrichment_status: Optional[str] = None
    enrichment_source: Optional[str] = None
    enrichment_confidence: Optional[float] = None
    enrichment_last_error: Optional[str] = None
    enrichment_last_checked_at: Optional[str] = None


UPSERT_SQL = """
INSERT INTO leads (
  run_id,
  business_name,
  phone,
  email,
  phone_source,
  email_source,
  phone_confidence,
  email_confidence,
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
  service_areas_json,
  enrichment_status,
  enrichment_source,
  enrichment_confidence,
  enrichment_last_error,
  enrichment_last_checked_at
)
VALUES (
  :run_id,
  :business_name,
  :phone,
  :email,
  :phone_source,
  :email_source,
  :phone_confidence,
  :email_confidence,
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
  :service_areas_json,
  :enrichment_status,
  :enrichment_source,
  :enrichment_confidence,
  :enrichment_last_error,
  :enrichment_last_checked_at
)
ON CONFLICT(website_url_normalized) DO UPDATE SET
  run_id = excluded.run_id,
  -- Preservation rule (H-5 fix): contact/identity/enrichment columns are
  -- protected against destructive updates — a NULL, empty, whitespace-only
  -- (or, for service areas, '[]') incoming value never erases a previously
  -- stored valid value; an incoming valid value still overwrites (last-write-
  -- wins for valid→valid; phone/email additionally use better_contact).
  -- Intentionally NOT preserved (per-run state, replaced each run):
  --   platform/complexity/load_speed, score, priority, extraction_success,
  --   extracted_at, last_error — matching the delete-then-insert semantics
  --   used for detections/audits/scores/opportunities.
  business_name = COALESCE(NULLIF(trim(excluded.business_name), ''), leads.business_name),
  phone = excluded.phone,
  email = excluded.email,
  phone_source = excluded.phone_source,
  email_source = excluded.email_source,
  phone_confidence = excluded.phone_confidence,
  email_confidence = excluded.email_confidence,
  website_url = COALESCE(NULLIF(trim(excluded.website_url), ''), leads.website_url),
  platform = excluded.platform,
  complexity = excluded.complexity,
  load_speed = excluded.load_speed,
  city = COALESCE(NULLIF(trim(excluded.city), ''), leads.city),
  state = COALESCE(NULLIF(trim(excluded.state), ''), leads.state),
  category = COALESCE(NULLIF(trim(excluded.category), ''), leads.category),
  score = excluded.score,
  priority = excluded.priority,
  extraction_success = excluded.extraction_success,
  extracted_at = datetime('now'),
  last_error = excluded.last_error,
  source = COALESCE(NULLIF(trim(excluded.source), ''), leads.source),
  osm_id = COALESCE(NULLIF(trim(excluded.osm_id), ''), leads.osm_id),
  osm_type = COALESCE(NULLIF(trim(excluded.osm_type), ''), leads.osm_type),
  latitude = COALESCE(excluded.latitude, leads.latitude),
  longitude = COALESCE(excluded.longitude, leads.longitude),
  address = COALESCE(NULLIF(trim(excluded.address), ''), leads.address),
  opening_hours = COALESCE(NULLIF(trim(excluded.opening_hours), ''), leads.opening_hours),
  country = COALESCE(NULLIF(trim(excluded.country), ''), leads.country),
  owner_name = COALESCE(NULLIF(trim(excluded.owner_name), ''), leads.owner_name),
  postal_code = COALESCE(NULLIF(trim(excluded.postal_code), ''), leads.postal_code),
  facebook_url = COALESCE(NULLIF(trim(excluded.facebook_url), ''), leads.facebook_url),
  instagram_url = COALESCE(NULLIF(trim(excluded.instagram_url), ''), leads.instagram_url),
  linkedin_url = COALESCE(NULLIF(trim(excluded.linkedin_url), ''), leads.linkedin_url),
  twitter_url = COALESCE(NULLIF(trim(excluded.twitter_url), ''), leads.twitter_url),
  youtube_url = COALESCE(NULLIF(trim(excluded.youtube_url), ''), leads.youtube_url),
  whatsapp_url = COALESCE(NULLIF(trim(excluded.whatsapp_url), ''), leads.whatsapp_url),
  contact_page_url = COALESCE(NULLIF(trim(excluded.contact_page_url), ''), leads.contact_page_url),
  contact_form_url = COALESCE(NULLIF(trim(excluded.contact_form_url), ''), leads.contact_form_url),
  google_maps_url = COALESCE(NULLIF(trim(excluded.google_maps_url), ''), leads.google_maps_url),
  service_areas_json = CASE
    WHEN excluded.service_areas_json IS NULL
      OR trim(excluded.service_areas_json) = ''
      OR excluded.service_areas_json = '[]'
    THEN leads.service_areas_json
    ELSE excluded.service_areas_json
  END,
  enrichment_status = COALESCE(excluded.enrichment_status, leads.enrichment_status),
  enrichment_source = COALESCE(excluded.enrichment_source, leads.enrichment_source),
  enrichment_confidence = COALESCE(excluded.enrichment_confidence, leads.enrichment_confidence),
  enrichment_last_error = COALESCE(excluded.enrichment_last_error, leads.enrichment_last_error),
  enrichment_last_checked_at = COALESCE(excluded.enrichment_last_checked_at, leads.enrichment_last_checked_at);
"""


def _clean_key_part(value: Optional[str]) -> str:
    return (value or "").strip().lower()


# Text fields protected by the missing-value preservation rule: an incoming
# value that is NULL/empty/whitespace-only counts as missing and must not
# erase a previously stored value (bug.md H-5). Normalizing here — inside
# upsert_lead — protects every caller, not just main.py.
_PRESERVED_TEXT_FIELDS = (
    "website_url",
    "business_name",
    "city",
    "state",
    "category",
    "source",
    "osm_id",
    "osm_type",
    "address",
    "opening_hours",
    "country",
    "owner_name",
    "postal_code",
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


def _blank_to_none(value: Optional[str]) -> Optional[str]:
    """Whitespace-only strings count as missing input."""
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _normalize_blank_fields(lead: LeadUpsert) -> LeadUpsert:
    """Treat empty/whitespace-only protected text fields as missing (None)."""
    changed = False
    updates: dict[str, Optional[str]] = {}
    for name in _PRESERVED_TEXT_FIELDS:
        value = getattr(lead, name)
        cleaned = _blank_to_none(value)
        if cleaned is not value and cleaned != value:
            updates[name] = cleaned
            changed = True
    if not changed:
        return lead
    return replace(lead, **updates)


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
    # Missing-value preservation (H-5): blank text fields count as missing
    # before any dedupe/merge/SQL logic sees them.
    lead = _normalize_blank_fields(lead)
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

    # Preservation: a weaker incoming value never overwrites a stronger stored
    # one (same validity rules, source rank, then confidence as the source
    # engine uses); a stronger incoming value still replaces the stored one.
    existing = connection.execute(
        "SELECT phone, email, phone_source, email_source, phone_confidence, email_confidence "
        "FROM leads WHERE website_url_normalized = ?",
        (website_url_normalized,),
    ).fetchone()
    if existing is not None:
        phone, phone_source, phone_confidence = better_contact(
            existing[0], existing[2], existing[4], lead.phone, lead.phone_source, lead.phone_confidence
        )
        email, email_source, email_confidence = better_contact(
            existing[1], existing[3], existing[5], lead.email, lead.email_source, lead.email_confidence
        )
    else:
        phone, phone_source, phone_confidence = lead.phone, lead.phone_source, lead.phone_confidence
        email, email_source, email_confidence = lead.email, lead.email_source, lead.email_confidence

    connection.execute(
        UPSERT_SQL,
        {
            "run_id": lead.run_id,
            "business_name": lead.business_name,
            "phone": phone,
            "email": email,
            "phone_source": phone_source,
            "email_source": email_source,
            "phone_confidence": phone_confidence,
            "email_confidence": email_confidence,
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
            "enrichment_status": lead.enrichment_status,
            "enrichment_source": lead.enrichment_source,
            "enrichment_confidence": lead.enrichment_confidence,
            "enrichment_last_error": lead.enrichment_last_error,
            "enrichment_last_checked_at": lead.enrichment_last_checked_at,
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
