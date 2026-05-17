from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Optional

from src.storage.normalization import normalize_url_for_dedupe


@dataclass(frozen=True)
class LeadUpsert:
    website_url: Optional[str]
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
  last_error
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
  :last_error
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
  last_error = excluded.last_error;
"""


def upsert_lead(connection: sqlite3.Connection, lead: LeadUpsert) -> str:
    website_url_normalized = normalize_url_for_dedupe(lead.website_url)
    if not website_url_normalized:
        raise ValueError("website_url is required for upsert (after normalization it was empty)")

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
        },
    )
    connection.commit()
    return website_url_normalized
