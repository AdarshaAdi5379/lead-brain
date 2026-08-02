from __future__ import annotations

import sqlite3
from pathlib import Path


SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS scraping_runs (
  run_id INTEGER PRIMARY KEY AUTOINCREMENT,
  started_at TEXT NOT NULL,
  completed_at TEXT,
  total_urls_processed INTEGER NOT NULL DEFAULT 0,
  successful_extractions INTEGER NOT NULL DEFAULT 0,
  failed_extractions INTEGER NOT NULL DEFAULT 0,
  total_cost_usd REAL NOT NULL DEFAULT 0.0
);

CREATE TABLE IF NOT EXISTS leads (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id INTEGER,

  business_name TEXT,
  phone TEXT,
  email TEXT,

  website_url TEXT,
  website_url_normalized TEXT NOT NULL,

  platform TEXT,
  complexity TEXT,
  load_speed TEXT,

  city TEXT,
  state TEXT,
  category TEXT,

  score INTEGER,
  priority TEXT,

  extraction_success INTEGER NOT NULL DEFAULT 0,
  extracted_at TEXT NOT NULL DEFAULT (datetime('now')),

  outreach_sent INTEGER NOT NULL DEFAULT 0,
  outreach_sent_at TEXT,
  notes TEXT,

  last_error TEXT,

  source TEXT,
  osm_id TEXT,
  osm_type TEXT,
  latitude REAL,
  longitude REAL,
  address TEXT,
  opening_hours TEXT,
  country TEXT,

  FOREIGN KEY (run_id) REFERENCES scraping_runs(run_id) ON DELETE SET NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_leads_website_url_normalized
  ON leads(website_url_normalized);

CREATE INDEX IF NOT EXISTS ix_leads_score ON leads(score);
CREATE INDEX IF NOT EXISTS ix_leads_priority ON leads(priority);

CREATE TABLE IF NOT EXISTS technology_detections (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  lead_id INTEGER NOT NULL,
  technology_name TEXT NOT NULL,
  category TEXT NOT NULL,
  confidence INTEGER NOT NULL,
  evidence TEXT NOT NULL DEFAULT '[]',
  detected_at TEXT NOT NULL DEFAULT (datetime('now')),
  FOREIGN KEY (lead_id) REFERENCES leads(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_technology_detections_lead_id
  ON technology_detections(lead_id);

CREATE INDEX IF NOT EXISTS ix_technology_detections_category
  ON technology_detections(category);

CREATE TABLE IF NOT EXISTS seo_audits (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  lead_id INTEGER NOT NULL,
  site_score INTEGER NOT NULL,
  overall_health TEXT NOT NULL,
  total_pages_audited INTEGER NOT NULL DEFAULT 0,
  html_pages INTEGER NOT NULL DEFAULT 0,
  pages_with_title INTEGER NOT NULL DEFAULT 0,
  pages_with_meta_description INTEGER NOT NULL DEFAULT 0,
  pages_with_h1 INTEGER NOT NULL DEFAULT 0,
  pages_with_multiple_h1 INTEGER NOT NULL DEFAULT 0,
  pages_with_noindex INTEGER NOT NULL DEFAULT 0,
  pages_with_canonical INTEGER NOT NULL DEFAULT 0,
  pages_with_json_ld INTEGER NOT NULL DEFAULT 0,
  pages_with_images_missing_alt INTEGER NOT NULL DEFAULT 0,
  pages_with_duplicate_titles INTEGER NOT NULL DEFAULT 0,
  pages_with_duplicate_descriptions INTEGER NOT NULL DEFAULT 0,
  pages_with_thin_content INTEGER NOT NULL DEFAULT 0,
  robots_txt_detected INTEGER NOT NULL DEFAULT 0,
  sitemap_detected INTEGER NOT NULL DEFAULT 0,
  severity_summary TEXT NOT NULL DEFAULT '[]',
  raw_summary_json TEXT NOT NULL DEFAULT '{}',
  audited_at TEXT NOT NULL DEFAULT (datetime('now')),
  FOREIGN KEY (lead_id) REFERENCES leads(id) ON DELETE CASCADE
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_seo_audits_lead_id
  ON seo_audits(lead_id);

CREATE INDEX IF NOT EXISTS ix_seo_audits_site_score
  ON seo_audits(site_score);

CREATE TABLE IF NOT EXISTS seo_page_audits (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  seo_audit_id INTEGER NOT NULL,
  url TEXT NOT NULL,
  page_type TEXT,
  html_available INTEGER NOT NULL DEFAULT 0,
  title_present INTEGER NOT NULL DEFAULT 0,
  title_length INTEGER,
  meta_description_present INTEGER NOT NULL DEFAULT 0,
  meta_description_length INTEGER,
  h1_count INTEGER NOT NULL DEFAULT 0,
  h2_count INTEGER NOT NULL DEFAULT 0,
  canonical_present INTEGER NOT NULL DEFAULT 0,
  robots_meta INTEGER NOT NULL DEFAULT 0,
  viewport_present INTEGER NOT NULL DEFAULT 0,
  noindex INTEGER NOT NULL DEFAULT 0,
  nofollow INTEGER NOT NULL DEFAULT 0,
  word_count INTEGER NOT NULL DEFAULT 0,
  image_count INTEGER NOT NULL DEFAULT 0,
  images_missing_alt_count INTEGER NOT NULL DEFAULT 0,
  json_ld_present INTEGER NOT NULL DEFAULT 0,
  schema_present INTEGER NOT NULL DEFAULT 0,
  og_title_present INTEGER NOT NULL DEFAULT 0,
  og_description_present INTEGER NOT NULL DEFAULT 0,
  twitter_card_present INTEGER NOT NULL DEFAULT 0,
  internal_link_count INTEGER NOT NULL DEFAULT 0,
  score INTEGER NOT NULL DEFAULT 0,
  health TEXT NOT NULL DEFAULT 'Excellent',
  issues_json TEXT NOT NULL DEFAULT '[]',
  FOREIGN KEY (seo_audit_id) REFERENCES seo_audits(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_seo_page_audits_audit_id
  ON seo_page_audits(seo_audit_id);

CREATE INDEX IF NOT EXISTS ix_seo_page_audits_noindex
  ON seo_page_audits(noindex);

CREATE TABLE IF NOT EXISTS lead_scores (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  lead_id INTEGER NOT NULL,
  final_score INTEGER NOT NULL,
  priority_label TEXT NOT NULL,
  discovery_quality_score INTEGER NOT NULL DEFAULT 0,
  contactability_score INTEGER NOT NULL DEFAULT 0,
  technical_health_score INTEGER NOT NULL DEFAULT 0,
  seo_health_score INTEGER NOT NULL DEFAULT 0,
  content_strength_score INTEGER NOT NULL DEFAULT 0,
  trust_professionalism_score INTEGER NOT NULL DEFAULT 0,
  outreach_potential_score INTEGER NOT NULL DEFAULT 0,
  dimension_reasons_json TEXT NOT NULL DEFAULT '{}',
  top_positive_reasons_json TEXT NOT NULL DEFAULT '[]',
  top_negative_reasons_json TEXT NOT NULL DEFAULT '[]',
  recommended_outreach_angle TEXT NOT NULL DEFAULT '',
  scored_at TEXT NOT NULL DEFAULT (datetime('now')),
  FOREIGN KEY (lead_id) REFERENCES leads(id) ON DELETE CASCADE
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_lead_scores_lead_id
  ON lead_scores(lead_id);

CREATE INDEX IF NOT EXISTS ix_lead_scores_final_score
  ON lead_scores(final_score);
"""


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON;")
    return connection


def init_db(connection: sqlite3.Connection) -> None:
    connection.executescript(SCHEMA_SQL)
    _apply_migrations(connection)
    connection.commit()


def _apply_migrations(connection: sqlite3.Connection) -> None:
    """
    Simple in-place migrations for v1.

    We use CREATE TABLE IF NOT EXISTS for baseline schema, then ALTER TABLE
    for additive changes when the DB already exists.
    """

    lead_columns = {r["name"] for r in connection.execute("PRAGMA table_info(leads)").fetchall()}
    if "outreach_sent_at" not in lead_columns:
        connection.execute("ALTER TABLE leads ADD COLUMN outreach_sent_at TEXT")

    _ADDITIVE_LEAD_COLUMNS = [
        ("source", "TEXT"),
        ("osm_id", "TEXT"),
        ("osm_type", "TEXT"),
        ("latitude", "REAL"),
        ("longitude", "REAL"),
        ("address", "TEXT"),
        ("opening_hours", "TEXT"),
        ("country", "TEXT"),
    ]
    for column, column_type in _ADDITIVE_LEAD_COLUMNS:
        if column not in lead_columns:
            connection.execute(
                f"ALTER TABLE leads ADD COLUMN {column} {column_type}"
            )
