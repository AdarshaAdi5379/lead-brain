# Phase R2 regression suite: website identity preservation on the no-fetch
# path (Playwright unavailable / crawl impossible). Offline, temp DB only.
from __future__ import annotations

import csv
import unittest

import main
from src.storage.runs import start_run
from src.url_loader import SeedRow

from tests.search_fixtures import SearchTestDb


def make_seed(**overrides) -> SeedRow:
    base = {
        "business_name": "Test Business",
        "category": "plumber",
        "url": None,
        "city": "Austin",
        "state": "TX",
    }
    base.update(overrides)
    return SeedRow(**base)


def fetch_row(db, business_name: str = "Test Business"):
    return db.connection.execute(
        "SELECT * FROM leads WHERE business_name = ?", (business_name,)
    ).fetchone()


class TestWebsiteIdentityPreservation(unittest.TestCase):
    def setUp(self) -> None:
        self.db = SearchTestDb()

    def tearDown(self) -> None:
        self.db.close()

    """CRIT-1: a valid seed URL must survive the pipeline without crawling."""

    def test_csv_seed_with_url_playwright_unavailable(self) -> None:
        main._process_seed_no_fetch(
            self.db.connection, self.db.run_id, make_seed(url="https://example.com")
        )
        row = fetch_row(self.db)
        self.assertIsNotNone(row)
        self.assertEqual(row["website_url"], "https://example.com")
        self.assertEqual(row["extraction_success"], 0)
        self.assertIn("Playwright unavailable", row["last_error"] or "")
        self.assertNotIn("No website URL provided", row["last_error"] or "")
        # Real URL identity, NOT a synthetic biz:// key.
        self.assertTrue(row["website_url_normalized"].startswith("https://"))

    def test_csv_seed_without_url_unchanged(self) -> None:
        main._process_seed_no_fetch(self.db.connection, self.db.run_id, make_seed())
        row = fetch_row(self.db)
        self.assertIsNone(row["website_url"])
        self.assertTrue(row["website_url_normalized"].startswith("biz://"))
        self.assertEqual(row["last_error"], "No website URL provided")

    def test_osm_seed_with_url_preserved_with_contact_data(self) -> None:
        seed = make_seed(
            url="https://osmbiz.example.com",
            source="openstreetmap",
            osm_id="n123",
            osm_type="node",
            phone="+1-512-555-0100",
            email="hello@osmbiz.example.com",
            address="12 Congress Ave",
            postal_code="78701",
            country="US",
            latitude=30.26,
            longitude=-97.74,
        )
        main._process_seed_no_fetch(self.db.connection, self.db.run_id, seed)
        row = fetch_row(self.db)
        self.assertEqual(row["website_url"], "https://osmbiz.example.com")
        self.assertEqual(row["source"], "openstreetmap")
        self.assertEqual(row["osm_id"], "n123")
        self.assertEqual(row["phone"], "+1-512-555-0100")
        self.assertEqual(row["email"], "hello@osmbiz.example.com")
        self.assertEqual(row["address"], "12 Congress Ave")
        self.assertEqual(row["postal_code"], "78701")
        self.assertEqual(row["country"], "US")
        self.assertIn("Playwright unavailable", row["last_error"])

    def test_osm_seed_without_url_biz_fallback_intact(self) -> None:
        main._process_seed_no_fetch(
            self.db.connection,
            self.db.run_id,
            make_seed(source="openstreetmap", osm_id="n9"),
        )
        row = fetch_row(self.db)
        self.assertIsNone(row["website_url"])
        self.assertTrue(row["website_url_normalized"].startswith("biz://"))
        self.assertEqual(row["osm_id"], "n9")

    def test_unsafe_url_still_rejected_not_preserved_as_identity(self) -> None:
        # R1 boundary holds: unsafe URLs are rejected, never stored/fetched.
        seed = make_seed(
            url=None,
            url_error=(
                "Invalid/unsafe website URL "
                "(Unsafe URL: private or non-public IP address)"
            ),
        )
        main._process_seed_no_fetch(self.db.connection, self.db.run_id, seed)
        row = fetch_row(self.db)
        self.assertIsNone(row["website_url"])
        self.assertIn("Invalid/unsafe website URL", row["last_error"] or "")


class TestDedupeAcrossRuns(unittest.TestCase):
    def setUp(self) -> None:
        self.db = SearchTestDb()

    def tearDown(self) -> None:
        self.db.close()

    """Requirement 12: no duplicate solely because a crawl could not happen."""

    def test_repeat_run_same_website_single_row(self) -> None:
        seed = make_seed(url="https://repeat.example.com", business_name="Repeat Co")
        main._process_seed_no_fetch(self.db.connection, self.db.run_id, seed)
        rows_before = self.db.connection.execute(
            "SELECT COUNT(*) FROM leads"
        ).fetchone()[0]

        run2 = start_run(self.db.connection)
        main._process_seed_no_fetch(self.db.connection, run2, seed)

        rows_after = self.db.connection.execute(
            "SELECT COUNT(*) FROM leads"
        ).fetchone()[0]
        self.assertEqual(rows_before, 1)
        self.assertEqual(rows_after, 1)
        row = fetch_row(self.db, "Repeat Co")
        self.assertEqual(row["website_url"], "https://repeat.example.com")


class TestDerivedDataStaysAssociated(unittest.TestCase):
    def setUp(self) -> None:
        self.db = SearchTestDb()

    def tearDown(self) -> None:
        self.db.close()

    """Requirement 13: a no-fetch re-run must not detach derived intelligence."""

    def test_rerun_keeps_identity_and_replaces_score(self) -> None:
        seed = make_seed(url="https://derived.example.com", business_name="Derived Co")
        main._process_seed_no_fetch(self.db.connection, self.db.run_id, seed)
        lead_one = fetch_row(self.db, "Derived Co")
        score_before = self.db.connection.execute(
            "SELECT COUNT(*) FROM lead_scores WHERE lead_id = ?", (lead_one["id"],)
        ).fetchone()[0]
        self.assertGreaterEqual(score_before, 1)

        run2 = start_run(self.db.connection)
        main._process_seed_no_fetch(self.db.connection, run2, seed)

        lead_two = fetch_row(self.db, "Derived Co")
        self.assertEqual(lead_one["id"], lead_two["id"])
        self.assertEqual(lead_two["website_url"], "https://derived.example.com")
        score_after = self.db.connection.execute(
            "SELECT COUNT(*) FROM lead_scores WHERE lead_id = ?", (lead_two["id"],)
        ).fetchone()[0]
        self.assertGreaterEqual(score_after, 1)


class TestOnlyFailedRetryEligibility(unittest.TestCase):
    def setUp(self) -> None:
        self.db = SearchTestDb()

    def tearDown(self) -> None:
        self.db.close()

    """Requirement 8: failed no-fetch leads become retryable seeds."""

    def test_playwright_unavailable_lead_is_retryable(self) -> None:
        main._process_seed_no_fetch(
            self.db.connection,
            self.db.run_id,
            make_seed(url="https://retryme.example.com"),
        )
        seeds = main._load_failed_seeds_from_db(self.db.connection, limit=10)
        self.assertIn("https://retryme.example.com", [seed.url for seed in seeds])


class TestExportRetainsWebsiteAndDerivedColumns(unittest.TestCase):
    def setUp(self) -> None:
        self.db = SearchTestDb()

    def tearDown(self) -> None:
        self.db.close()

    """Requirement 7 / H-10: derived columns must not strand in the DB."""

    def _export_rows(self) -> list[dict]:
        out_path = main._export_csv_for_run(
            self.db.connection, run_id=self.db.run_id, min_score=0
        )
        try:
            with out_path.open(newline="", encoding="utf-8") as f:
                return [dict(row) for row in csv.DictReader(f)]
        finally:
            out_path.unlink(missing_ok=True)

    def test_export_for_no_fetch_leads(self) -> None:
        main._process_seed_no_fetch(
            self.db.connection,
            self.db.run_id,
            make_seed(url="https://exported.example.com", business_name="Exported Co"),
        )
        main._process_seed_no_fetch(
            self.db.connection,
            self.db.run_id,
            make_seed(business_name="No Site Co"),
        )
        rows_by_name = {row["business_name"]: row for row in self._export_rows()}
        exported = rows_by_name.get("Exported Co")
        nosite = rows_by_name.get("No Site Co")
        self.assertIsNotNone(exported)
        self.assertIsNotNone(nosite)

        # Website identity retained in the export...
        self.assertEqual(exported["website_url"], "https://exported.example.com")
        # ...and derived columns actually join for BOTH identity kinds.
        self.assertNotEqual(exported.get("final_score"), "")
        self.assertNotEqual(nosite.get("final_score"), "")


if __name__ == "__main__":
    unittest.main()

