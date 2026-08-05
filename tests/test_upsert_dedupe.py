import sqlite3
import unittest

from src.storage.db import init_db
from src.storage.leads import LeadUpsert, upsert_lead


class TestUpsertDedupe(unittest.TestCase):
    def setUp(self) -> None:
        self.connection = sqlite3.connect(":memory:")
        self.connection.row_factory = sqlite3.Row
        init_db(self.connection)

        # Create a run for FK checks.
        self.connection.execute("INSERT INTO scraping_runs (started_at) VALUES (datetime('now'))")
        self.run_id = int(self.connection.execute("SELECT run_id FROM scraping_runs").fetchone()["run_id"])

    def tearDown(self) -> None:
        self.connection.close()

    def test_upsert_allows_no_website_with_business_name(self) -> None:
        key1 = upsert_lead(
            self.connection,
            LeadUpsert(
                website_url=None,
                business_name="Acme Plumbing",
                city="Austin",
                state="TX",
                category="plumber",
                score=90,
                priority="Hot",
                run_id=self.run_id,
            ),
        )
        self.assertTrue(key1.startswith("biz://"))

    def test_upsert_dedupes_business_key(self) -> None:
        key1 = upsert_lead(
            self.connection,
            LeadUpsert(
                website_url=None,
                business_name="Acme Plumbing",
                city="Austin",
                state="TX",
                category="plumber",
                score=90,
                priority="Hot",
                run_id=self.run_id,
            ),
        )
        key2 = upsert_lead(
            self.connection,
            LeadUpsert(
                website_url=None,
                business_name="Acme Plumbing",
                city="Austin",
                state="TX",
                category="plumber",
                score=50,
                priority="Warm",
                run_id=self.run_id,
            ),
        )
        self.assertEqual(key1, key2)
        row = self.connection.execute(
            "SELECT score, priority FROM leads WHERE website_url_normalized = ?",
            (key1,),
        ).fetchone()
        self.assertEqual(int(row["score"]), 50)
        self.assertEqual(row["priority"], "Warm")

    def test_upsert_persists_contact_fields(self) -> None:
        import json

        upsert_lead(
            self.connection,
            LeadUpsert(
                website_url="https://acme.example.com/",
                business_name="Acme Plumbing",
                city="Austin",
                state="TX",
                category="plumber",
                score=70,
                priority="Warm",
                run_id=self.run_id,
                owner_name="Bob Acme",
                postal_code="78701",
                facebook_url="https://www.facebook.com/acmeplumbing",
                contact_page_url="https://acme.example.com/contact",
                contact_form_url="https://acme.example.com/submit-contact",
                google_maps_url="https://www.google.com/maps/search/?api=1&query=30.267200,-97.743100",
                service_areas=["Austin", "Round Rock"],
            ),
        )
        row = self.connection.execute(
            "SELECT owner_name, postal_code, facebook_url, contact_page_url, "
            "contact_form_url, google_maps_url, service_areas_json FROM leads"
        ).fetchone()
        self.assertEqual(row["owner_name"], "Bob Acme")
        self.assertEqual(row["postal_code"], "78701")
        self.assertEqual(row["facebook_url"], "https://www.facebook.com/acmeplumbing")
        self.assertEqual(row["contact_page_url"], "https://acme.example.com/contact")
        self.assertEqual(row["contact_form_url"], "https://acme.example.com/submit-contact")
        self.assertEqual(
            row["google_maps_url"],
            "https://www.google.com/maps/search/?api=1&query=30.267200,-97.743100",
        )
        self.assertEqual(json.loads(row["service_areas_json"]), ["Austin", "Round Rock"])


if __name__ == "__main__":
    unittest.main()

