import sqlite3
import unittest

from src.fingerprinting.base import Detection
from src.storage.db import init_db
from src.storage.leads import LeadUpsert, upsert_lead
from src.storage.technologies import (
    detections_by_lead,
    detections_for_run,
    get_lead_id_by_url,
    replace_detections,
)


def _make_db() -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    init_db(connection)
    return connection


class TestTechnologyDetectionsStorage(unittest.TestCase):
    def test_replace_and_read_back(self) -> None:
        connection = _make_db()
        try:
            normalized = upsert_lead(
                connection,
                LeadUpsert(website_url="https://acme.example.com/", business_name="Acme"),
            )
            lead_id = get_lead_id_by_url(connection, normalized)
            self.assertIsNotNone(lead_id)

            detections = [
                Detection(name="WordPress", category="cms", confidence=70, evidence=("generator=WP",)),
                Detection(name="Cloudflare", category="hosting", confidence=55),
            ]
            replace_detections(connection, lead_id, detections)

            by_lead = detections_by_lead(connection)
            stored = by_lead.get(lead_id, [])
            self.assertEqual(len(stored), 2)
            names = {row["technology_name"] for row in stored}
            self.assertIn("WordPress", names)
            wordpress = next(r for r in stored if r["technology_name"] == "WordPress")
            self.assertEqual(wordpress["confidence"], 70)
            self.assertEqual(wordpress["evidence"], ["generator=WP"])
        finally:
            connection.close()

    def test_replace_is_deterministic_on_rerun(self) -> None:
        connection = _make_db()
        try:
            normalized = upsert_lead(
                connection, LeadUpsert(website_url="https://acme.example.com/")
            )
            lead_id = get_lead_id_by_url(connection, normalized)

            replace_detections(
                connection, lead_id, [Detection("WordPress", "cms", 70)]
            )
            replace_detections(
                connection, lead_id, [Detection("Shopify", "cms", 80)]
            )

            by_lead = detections_by_lead(connection)
            stored = by_lead.get(lead_id, [])
            self.assertEqual(len(stored), 1)
            self.assertEqual(stored[0]["technology_name"], "Shopify")
        finally:
            connection.close()

    def test_detections_for_run_groups_by_run(self) -> None:
        connection = _make_db()
        try:
            connection.execute(
                "INSERT INTO scraping_runs (started_at) VALUES (datetime('now'))"
            )
            run_id = connection.execute(
                "SELECT last_insert_rowid() AS rid"
            ).fetchone()["rid"]

            normalized = upsert_lead(
                connection,
                LeadUpsert(
                    website_url="https://acme.example.com/",
                    business_name="Acme",
                    run_id=run_id,
                ),
            )
            lead_id = get_lead_id_by_url(connection, normalized)
            replace_detections(
                connection, lead_id, [Detection("WordPress", "cms", 60)]
            )

            rows = detections_for_run(connection, run_id)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["technology_name"], "WordPress")
        finally:
            connection.close()


if __name__ == "__main__":
    unittest.main()