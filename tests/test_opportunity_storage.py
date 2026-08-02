import sqlite3
import unittest

from src.opportunities import detect_opportunities
from src.storage.db import init_db
from src.storage.leads import LeadUpsert, upsert_lead
from src.storage.opportunities import (
    opportunities_by_lead,
    opportunities_for_run,
    replace_opportunities,
)
from tests.scoring_fixtures import weak_site_inputs
from tests.test_opportunity_detectors import _score_for


def _make_db() -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    init_db(connection)
    return connection


def _insert_lead(connection: sqlite3.Connection, run_id: int, name: str = "Acme") -> str:
    return upsert_lead(
        connection,
        LeadUpsert(
            website_url="https://acme.example.com",
            business_name=name,
            phone="512-555-0100",
            email="acme@example.com",
            city="Austin",
            state="TX",
            category="plumber",
            run_id=run_id,
        ),
    )


class TestOpportunityStorage(unittest.TestCase):
    def test_replace_and_read_back(self) -> None:
        connection = _make_db()
        try:
            run_id = connection.execute(
                "INSERT INTO scraping_runs (started_at) VALUES (datetime('now'))"
            ).lastrowid
            normalized = _insert_lead(connection, run_id)
            lead_id = int(
                connection.execute(
                    "SELECT id FROM leads WHERE website_url_normalized = ?", (normalized,)
                ).fetchone()["id"]
            )

            report = detect_opportunities(weak_site_inputs(), _score_for(weak_site_inputs()))
            inserted = replace_opportunities(connection, lead_id, report)
            self.assertEqual(inserted, report.opportunity_count)
            self.assertGreater(inserted, 0)

            by_lead = opportunities_by_lead(connection)
            rows = by_lead.get(lead_id)
            self.assertIsNotNone(rows)
            self.assertEqual(len(rows), report.opportunity_count)
            self.assertEqual(rows[0]["category"], report.opportunities[0].category)
            self.assertEqual(rows[0]["priority"], report.opportunity_priority)
            self.assertEqual(rows[0]["recommended_services"], list(report.opportunities[0].recommended_services))
            self.assertEqual(rows[0]["evidence"], list(report.opportunities[0].evidence))

            for_run = opportunities_for_run(connection, run_id)
            self.assertEqual(len(for_run), report.opportunity_count)
        finally:
            connection.close()

    def test_replace_is_delete_then_insert(self) -> None:
        connection = _make_db()
        try:
            run_id = connection.execute(
                "INSERT INTO scraping_runs (started_at) VALUES (datetime('now'))"
            ).lastrowid
            normalized = _insert_lead(connection, run_id)
            lead_id = int(
                connection.execute(
                    "SELECT id FROM leads WHERE website_url_normalized = ?", (normalized,)
                ).fetchone()["id"]
            )

            report = detect_opportunities(weak_site_inputs(), _score_for(weak_site_inputs()))
            replace_opportunities(connection, lead_id, report)
            replace_opportunities(connection, lead_id, report)

            count = connection.execute(
                "SELECT COUNT(*) FROM business_opportunities WHERE lead_id = ?", (lead_id,)
            ).fetchone()[0]
            self.assertEqual(count, report.opportunity_count)
        finally:
            connection.close()

    def test_opportunities_removed_when_lead_deleted(self) -> None:
        connection = _make_db()
        try:
            run_id = connection.execute(
                "INSERT INTO scraping_runs (started_at) VALUES (datetime('now'))"
            ).lastrowid
            normalized = _insert_lead(connection, run_id)
            lead_id = int(
                connection.execute(
                    "SELECT id FROM leads WHERE website_url_normalized = ?", (normalized,)
                ).fetchone()["id"]
            )

            report = detect_opportunities(weak_site_inputs(), _score_for(weak_site_inputs()))
            replace_opportunities(connection, lead_id, report)

            connection.execute("DELETE FROM leads WHERE id = ?", (lead_id,))
            connection.commit()
            remaining = connection.execute(
                "SELECT COUNT(*) FROM business_opportunities WHERE lead_id = ?", (lead_id,)
            ).fetchone()[0]
            self.assertEqual(remaining, 0)
        finally:
            connection.close()


if __name__ == "__main__":
    unittest.main()
