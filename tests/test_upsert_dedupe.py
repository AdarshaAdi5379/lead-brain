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


if __name__ == "__main__":
    unittest.main()

