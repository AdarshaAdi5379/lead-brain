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
  notes TEXT,

  last_error TEXT,

  FOREIGN KEY (run_id) REFERENCES scraping_runs(run_id) ON DELETE SET NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_leads_website_url_normalized
  ON leads(website_url_normalized);

CREATE INDEX IF NOT EXISTS ix_leads_score ON leads(score);
CREATE INDEX IF NOT EXISTS ix_leads_priority ON leads(priority);
"""


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON;")
    return connection


def init_db(connection: sqlite3.Connection) -> None:
    connection.executescript(SCHEMA_SQL)
    connection.commit()

