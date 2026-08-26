# Phase R3 regression suite: upsert contact preservation (bug.md H-5).
# A later lead upsert carrying NULL/empty/whitespace values must never erase
# previously stored contact/identity data, while new valid data still lands.
from __future__ import annotations

import csv
import unittest

import main
from src.storage.leads import LeadUpsert, upsert_lead

from tests.search_fixtures import SearchTestDb

URL = "https://preserved.example.com"


def rich_lead(**overrides) -> LeadUpsert:
    """A fully-populated discovery/OSM-style lead."""
    base = dict(
        website_url=URL,
        business_name="Preserved Co",
        phone="+1-512-555-0100",
        email="owner@preserved.example.com",
        source="openstreetmap",
        osm_id="n42",
        osm_type="node",
        latitude=30.2672,
        longitude=-97.7431,
        address="12 Congress Ave",
        opening_hours="Mo-Fr 09:00-17:00",
        country="US",
        owner_name="Jane Owner",
        postal_code="78701",
        facebook_url="https://facebook.com/preservedco",
        instagram_url="https://instagram.com/preservedco",
        contact_page_url=f"{URL}/contact",
        contact_form_url=f"{URL}/contact-form",
        service_areas=["Austin", "Round Rock"],
    )
    base.update(overrides)
    return LeadUpsert(**base)


def bare_lead(**overrides) -> LeadUpsert:
    """A minimal later-run lead for the same identity (crawl found nothing)."""
    base = dict(
        website_url=URL,
        business_name="Preserved Co",
        dedupe_key=None,
    )
    # Same stored identity without relying on website_url re-normalization:
    # callers may pass dedupe_key explicitly when the crawl path has no URL.
    if overrides.get("website_url") is None and "dedupe_key" not in overrides:
        base["dedupe_key"] = "https://preserved.example.com"
        base["website_url"] = None
    base.update(overrides)
    return LeadUpsert(**base)


class TestNullOverwritePreservation(unittest.TestCase):
    def setUp(self) -> None:
        self.db = SearchTestDb()

    def tearDown(self) -> None:
        self.db.close()

    def _row(self) -> object:
        return self.db.connection.execute(
            "SELECT * FROM leads WHERE website_url_normalized LIKE '%preserved.example.com'"
        ).fetchone()

    def test_existing_valid_incoming_null_keeps_all_fields(self) -> None:
        cx = self.db.connection
        upsert_lead(cx, rich_lead())
        upsert_lead(cx, bare_lead())
        row = self._row()
        self.assertEqual(row["phone"], "+1-512-555-0100")
        self.assertEqual(row["email"], "owner@preserved.example.com")
        self.assertEqual(row["address"], "12 Congress Ave")
        self.assertEqual(row["country"], "US")
        self.assertEqual(row["opening_hours"], "Mo-Fr 09:00-17:00")
        self.assertEqual(row["postal_code"], "78701")
        self.assertEqual(row["owner_name"], "Jane Owner")
        self.assertEqual(row["facebook_url"], "https://facebook.com/preservedco")
        self.assertEqual(row["instagram_url"], "https://instagram.com/preservedco")
        self.assertEqual(row["contact_page_url"], f"{URL}/contact")
        self.assertEqual(row["contact_form_url"], f"{URL}/contact-form")
        self.assertEqual(row["osm_id"], "n42")
        self.assertEqual(row["osm_type"], "node")
        self.assertEqual(row["source"], "openstreetmap")
        self.assertAlmostEqual(row["latitude"], 30.2672)
        self.assertAlmostEqual(row["longitude"], -97.7431)
        self.assertIn("Austin", row["service_areas_json"])
        self.assertEqual(row["business_name"], "Preserved Co")

    def test_website_identity_survives_null_incoming(self) -> None:
        cx = self.db.connection
        upsert_lead(cx, rich_lead())
        upsert_lead(cx, bare_lead())
        row = self._row()
        self.assertEqual(row["website_url"], URL)

    def test_empty_and_whitespace_incoming_values_keep_existing(self) -> None:
        cx = self.db.connection
        upsert_lead(cx, rich_lead())
        upsert_lead(
            cx,
            LeadUpsert(
                website_url=URL,
                business_name="Preserved Co",
                phone="",
                email="   ",
                instagram_url="   ",
                facebook_url="",
                address="\t ",
                service_areas=[],
            ),
        )
        row = self._row()
        self.assertEqual(row["phone"], "+1-512-555-0100")
        self.assertEqual(row["email"], "owner@preserved.example.com")
        self.assertEqual(row["instagram_url"], "https://instagram.com/preservedco")
        self.assertEqual(row["facebook_url"], "https://facebook.com/preservedco")
        self.assertEqual(row["address"], "12 Congress Ave")
        self.assertIn("Austin", row["service_areas_json"])

    def test_lat_lon_zero_is_valid_not_missing(self) -> None:
        cx = self.db.connection
        # 0.0 coordinates are legitimate (e.g. equator businesses) and must store.
        upsert_lead(cx, LeadUpsert(website_url="https://zero.example.com", business_name="Zero Co", latitude=0.0, longitude=0.0))
        row = cx.execute("SELECT latitude, longitude FROM leads WHERE business_name='Zero Co'").fetchone()
        self.assertEqual(row["latitude"], 0.0)
        self.assertEqual(row["longitude"], 0.0)
        # NULL incoming must not erase a stored non-zero coordinate.
        upsert_lead(cx, rich_lead())
        upsert_lead(cx, bare_lead())
        preserved = self._row()
        self.assertAlmostEqual(preserved["latitude"], 30.2672)


class TestNewDataStillWritten(unittest.TestCase):
    """The inverse rule: previously-empty fields must still be populated."""

    def setUp(self) -> None:
        self.db = SearchTestDb()

    def tearDown(self) -> None:
        self.db.close()

    def _row(self, name: str):
        return self.db.connection.execute(
            "SELECT * FROM leads WHERE business_name = ?", (name,)
        ).fetchone()

    def test_existing_null_incoming_valid_stores_values(self) -> None:
        cx = self.db.connection
        upsert_lead(cx, LeadUpsert(website_url="https://fill.example.com", business_name="Fill Co"))
        upsert_lead(
            cx,
            LeadUpsert(
                website_url="https://fill.example.com",
                business_name="Fill Co",
                phone="+1-512-555-0199",
                email="hello@fill.example.com",
                address="9 New St",
                instagram_url="https://instagram.com/fillco",
                contact_page_url="https://fill.example.com/contact",
                latitude=31.0,
                longitude=-98.0,
            ),
        )
        row = self._row("Fill Co")
        self.assertEqual(row["phone"], "+1-512-555-0199")
        self.assertEqual(row["email"], "hello@fill.example.com")
        self.assertEqual(row["address"], "9 New St")
        self.assertEqual(row["instagram_url"], "https://instagram.com/fillco")
        self.assertEqual(row["contact_page_url"], "https://fill.example.com/contact")
        self.assertEqual(row["latitude"], 31.0)

    def test_valid_to_valid_stays_last_write_wins_for_non_phone_fields(self) -> None:
        cx = self.db.connection
        upsert_lead(cx, rich_lead(address="12 Congress Ave"))
        upsert_lead(cx, rich_lead(address="500 New Plaza"))
        row = cx.execute(
            "SELECT address FROM leads WHERE business_name='Preserved Co'"
        ).fetchone()
        # Documented intent: newer valid value wins for contact fields other
        # than phone/email (which keep better_contact rank semantics).
        self.assertEqual(row["address"], "500 New Plaza")

    def test_osm_to_crawl_scenario(self) -> None:
        cx = self.db.connection
        upsert_lead(
            cx,
            LeadUpsert(
                website_url=URL,
                business_name="Scenario Co",
                source="openstreetmap",
                osm_id="n7",
                phone="+1-512-555-0007",
                email="osm@scenario.example.com",
                address="7 OSM Way",
                opening_hours="Mo-Sa 10:00-18:00",
            ),
        )
        # Later crawl: no contact facts found anywhere.
        upsert_lead(
            cx,
            LeadUpsert(website_url=URL, business_name="Scenario Co"),
        )
        row = cx.execute(
            "SELECT * FROM leads WHERE business_name='Scenario Co'"
        ).fetchone()
        self.assertEqual(row["phone"], "+1-512-555-0007")
        self.assertEqual(row["email"], "osm@scenario.example.com")
        self.assertEqual(row["address"], "7 OSM Way")
        self.assertEqual(row["opening_hours"], "Mo-Sa 10:00-18:00")


class TestPipelineIntegrationPreservation(unittest.TestCase):
    """Requirement 13/14/15: preservation through the real pipeline path,
    exports, and the shared dashboard intelligence builder."""

    def setUp(self) -> None:
        self.db = SearchTestDb()

    def tearDown(self) -> None:
        self.db.close()

    def test_no_fetch_rerun_preserves_osm_facts_and_exports_them(self) -> None:
        from src.storage.search import leads_intelligence
        from src.url_loader import SeedRow

        cx = self.db.connection

        def seed(**kw):
            base = dict(
                business_name="Pipe Flow Co",
                category="plumber",
                url=None,
                city="Austin",
                state="TX",
                source="openstreetmap",
                osm_id="n99",
                osm_type="node",
            )
            base.update(kw)
            return SeedRow(**base)

        main._process_seed_no_fetch(
            cx,
            self.db.run_id,
            seed(url="https://pipeflow.example.com", phone="+1-512-555-0999", address="99 Pipe Rd", postal_code="78702"),
        )
        # Second run: bare CSV-style seed with the same website — no contact data.
        main._process_seed_no_fetch(cx, self.db.run_id, seed(url="https://pipeflow.example.com"))

        row = cx.execute(
            "SELECT * FROM leads WHERE business_name='Pipe Flow Co'"
        ).fetchone()
        self.assertEqual(row["website_url"], "https://pipeflow.example.com")
        self.assertEqual(row["osm_id"], "n99")
        self.assertEqual(row["phone"], "+1-512-555-0999")
        self.assertEqual(row["address"], "99 Pipe Rd")
        self.assertEqual(row["postal_code"], "78702")

        out_path = main._export_csv_for_run(cx, run_id=self.db.run_id, min_score=0)
        try:
            with out_path.open(newline="", encoding="utf-8") as f:
                rows = [dict(r) for r in csv.DictReader(f)]
        finally:
            out_path.unlink(missing_ok=True)
        exported = next(r for r in rows if r["business_name"] == "Pipe Flow Co")
        self.assertEqual(exported["website_url"], "https://pipeflow.example.com")
        self.assertEqual(exported["phone"], "+1-512-555-0999")
        self.assertEqual(exported["postal_code"], "78702")

        intel = leads_intelligence(cx)
        blocks = [i for i in intel.values() if i["lead"]["business_name"] == "Pipe Flow Co"]
        self.assertEqual(len(blocks), 1)
        block = blocks[0]
        self.assertIsNotNone(block["score"])
        self.assertEqual(block["lead"]["website_url"], "https://pipeflow.example.com")


if __name__ == "__main__":
    unittest.main()


