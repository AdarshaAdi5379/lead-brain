import sqlite3
import unittest

from src.storage.db import init_db


class TestDbMigrations(unittest.TestCase):
    def test_init_db_adds_outreach_sent_at_column(self) -> None:
        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row
        try:
            init_db(connection)
            cols = {r["name"] for r in connection.execute("PRAGMA table_info(leads)").fetchall()}
            self.assertIn("outreach_sent_at", cols)
        finally:
            connection.close()

    def test_init_db_adds_discovery_columns(self) -> None:
        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row
        try:
            init_db(connection)
            cols = {r["name"] for r in connection.execute("PRAGMA table_info(leads)").fetchall()}
            for column in ("source", "osm_id", "osm_type", "latitude", "longitude",
                           "address", "opening_hours", "country"):
                self.assertIn(column, cols, f"missing column: {column}")
        finally:
            connection.close()

    def test_migration_adds_columns_to_existing_db(self) -> None:
        """Simulate a pre-Phase-9 DB (original schema, no discovery columns)."""
        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row
        try:
            connection.executescript(
                """
                CREATE TABLE leads (
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
                  last_error TEXT
                )
                """
            )
            init_db(connection)
            cols = {r["name"] for r in connection.execute("PRAGMA table_info(leads)").fetchall()}
            self.assertIn("source", cols)
            self.assertIn("osm_id", cols)
            self.assertIn("country", cols)
            self.assertIn("longitude", cols)
        finally:
            connection.close()

    def test_init_db_creates_technology_detections_table(self) -> None:
        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row
        try:
            init_db(connection)
            tables = {
                r["name"]
                for r in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            self.assertIn("technology_detections", tables)
            cols = {
                r["name"]
                for r in connection.execute(
                    "PRAGMA table_info(technology_detections)"
                ).fetchall()
            }
            for column in ("lead_id", "technology_name", "category", "confidence", "evidence"):
                self.assertIn(column, cols)
        finally:
            connection.close()

    def test_init_db_creates_seo_tables(self) -> None:
        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row
        try:
            init_db(connection)
            tables = {
                r["name"]
                for r in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            self.assertIn("seo_audits", tables)
            self.assertIn("seo_page_audits", tables)

            site_cols = {
                r["name"]
                for r in connection.execute("PRAGMA table_info(seo_audits)").fetchall()
            }
            for column in (
                "lead_id",
                "site_score",
                "overall_health",
                "total_pages_audited",
                "pages_with_title",
                "pages_with_thin_content",
                "severity_summary",
                "raw_summary_json",
            ):
                self.assertIn(column, site_cols)

            page_cols = {
                r["name"]
                for r in connection.execute("PRAGMA table_info(seo_page_audits)").fetchall()
            }
            for column in (
                "seo_audit_id",
                "url",
                "title_present",
                "h1_count",
                "noindex",
                "images_missing_alt_count",
                "issues_json",
            ):
                self.assertIn(column, page_cols)

            indexes = {
                r["name"]
                for r in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='index'"
                ).fetchall()
            }
            self.assertIn("ux_seo_audits_lead_id", indexes)
        finally:
            connection.close()

