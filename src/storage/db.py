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

  owner_name TEXT,
  postal_code TEXT,
  facebook_url TEXT,
  instagram_url TEXT,
  linkedin_url TEXT,
  twitter_url TEXT,
  youtube_url TEXT,
  whatsapp_url TEXT,
  contact_page_url TEXT,
  contact_form_url TEXT,
  google_maps_url TEXT,
  service_areas_json TEXT,

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
  pages_with_mixed_content INTEGER NOT NULL DEFAULT 0,
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

CREATE TABLE IF NOT EXISTS visual_audits (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  lead_id INTEGER NOT NULL,
  visual_score INTEGER NOT NULL,
  visual_health_label TEXT NOT NULL,
  summary TEXT NOT NULL DEFAULT '',
  total_pages_audited INTEGER NOT NULL DEFAULT 0,
  pages_with_desktop_screenshot INTEGER NOT NULL DEFAULT 0,
  pages_with_mobile_screenshot INTEGER NOT NULL DEFAULT 0,
  pages_with_modern_design_signal INTEGER NOT NULL DEFAULT 0,
  pages_with_clutter_signal INTEGER NOT NULL DEFAULT 0,
  pages_with_weak_hierarchy_signal INTEGER NOT NULL DEFAULT 0,
  pages_with_weak_mobile_signal INTEGER NOT NULL DEFAULT 0,
  pages_with_weak_cta_signal INTEGER NOT NULL DEFAULT 0,
  pages_with_strong_brand_signal INTEGER NOT NULL DEFAULT 0,
  llm_summary TEXT,
  raw_summary_json TEXT NOT NULL DEFAULT '{}',
  audited_at TEXT NOT NULL DEFAULT (datetime('now')),
  FOREIGN KEY (lead_id) REFERENCES leads(id) ON DELETE CASCADE
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_visual_audits_lead_id
  ON visual_audits(lead_id);

CREATE INDEX IF NOT EXISTS ix_visual_audits_visual_score
  ON visual_audits(visual_score);

CREATE TABLE IF NOT EXISTS visual_page_audits (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  visual_audit_id INTEGER NOT NULL,
  url TEXT NOT NULL,
  page_type TEXT,
  screenshot_available INTEGER NOT NULL DEFAULT 0,
  mobile_screenshot_available INTEGER NOT NULL DEFAULT 0,
  screenshot_path TEXT,
  mobile_screenshot_path TEXT,
  screenshot_hash TEXT,
  visual_score INTEGER NOT NULL DEFAULT 0,
  layout_quality INTEGER NOT NULL DEFAULT 0,
  readability_quality INTEGER NOT NULL DEFAULT 0,
  branding_quality INTEGER NOT NULL DEFAULT 0,
  mobile_quality INTEGER NOT NULL DEFAULT 0,
  conversion_quality INTEGER NOT NULL DEFAULT 0,
  confidence REAL NOT NULL DEFAULT 0.0,
  issues_json TEXT NOT NULL DEFAULT '[]',
  strengths_json TEXT NOT NULL DEFAULT '[]',
  evidence_json TEXT NOT NULL DEFAULT '{}',
  FOREIGN KEY (visual_audit_id) REFERENCES visual_audits(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_visual_page_audits_audit_id
  ON visual_page_audits(visual_audit_id);

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
  visual_presentation_score INTEGER NOT NULL DEFAULT 0,
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

CREATE TABLE IF NOT EXISTS business_opportunities (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  lead_id INTEGER NOT NULL,
  category TEXT NOT NULL,
  label TEXT NOT NULL,
  score INTEGER NOT NULL,
  severity TEXT NOT NULL,
  confidence INTEGER NOT NULL DEFAULT 0,
  priority TEXT NOT NULL DEFAULT '',
  business_impact TEXT NOT NULL DEFAULT '',
  implementation_effort TEXT NOT NULL DEFAULT '',
  recommended_services_json TEXT NOT NULL DEFAULT '[]',
  evidence_json TEXT NOT NULL DEFAULT '[]',
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  FOREIGN KEY (lead_id) REFERENCES leads(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_business_opportunities_lead_id
  ON business_opportunities(lead_id);

CREATE INDEX IF NOT EXISTS ix_business_opportunities_category
  ON business_opportunities(category);

CREATE TABLE IF NOT EXISTS lead_embeddings (
  lead_id INTEGER PRIMARY KEY,
  document_hash TEXT NOT NULL,
  embedding_hash TEXT NOT NULL,
  embedder_id TEXT NOT NULL,
  document_text TEXT NOT NULL,
  metadata_json TEXT NOT NULL DEFAULT '{}',
  embedding_json TEXT NOT NULL DEFAULT '[]',
  embedding_dim INTEGER NOT NULL DEFAULT 0,
  updated_at TEXT NOT NULL DEFAULT (datetime('now')),
  FOREIGN KEY (lead_id) REFERENCES leads(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_lead_embeddings_updated_at
  ON lead_embeddings(updated_at);

CREATE TABLE IF NOT EXISTS chat_sessions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id TEXT NOT NULL UNIQUE,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS chat_messages (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id TEXT NOT NULL,
  role TEXT NOT NULL,
  message TEXT NOT NULL,
  retrieved_lead_ids_json TEXT NOT NULL DEFAULT '[]',
  intent TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS ix_chat_messages_session
  ON chat_messages(session_id, created_at);
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
        ("owner_name", "TEXT"),
        ("postal_code", "TEXT"),
        ("facebook_url", "TEXT"),
        ("instagram_url", "TEXT"),
        ("linkedin_url", "TEXT"),
        ("twitter_url", "TEXT"),
        ("youtube_url", "TEXT"),
        ("whatsapp_url", "TEXT"),
        ("contact_page_url", "TEXT"),
        ("contact_form_url", "TEXT"),
        ("google_maps_url", "TEXT"),
        ("service_areas_json", "TEXT"),
    ]
    for column, column_type in _ADDITIVE_LEAD_COLUMNS:
        if column not in lead_columns:
            connection.execute(
                f"ALTER TABLE leads ADD COLUMN {column} {column_type}"
            )

    seo_columns = {r["name"] for r in connection.execute("PRAGMA table_info(seo_audits)").fetchall()}
    if "pages_with_mixed_content" not in seo_columns:
        connection.execute(
            "ALTER TABLE seo_audits ADD COLUMN pages_with_mixed_content INTEGER NOT NULL DEFAULT 0"
        )

    visual_columns = {
        r["name"] for r in connection.execute("PRAGMA table_info(visual_audits)").fetchall()
    }
    if "llm_summary" not in visual_columns:
        connection.execute("ALTER TABLE visual_audits ADD COLUMN llm_summary TEXT")

    score_columns = {
        r["name"] for r in connection.execute("PRAGMA table_info(lead_scores)").fetchall()
    }
    if "visual_presentation_score" not in score_columns:
        connection.execute(
            "ALTER TABLE lead_scores ADD COLUMN visual_presentation_score INTEGER NOT NULL DEFAULT 0"
        )
