import sqlite3
import unittest

from src.scoring import score_site_lead
from src.storage.db import init_db
from src.storage.leads import LeadUpsert, upsert_lead
from src.storage.scores import replace_score, score_for_lead, scores_by_lead, scores_for_run
from tests.scoring_fixtures import strong_site_inputs


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


class TestScoringStorage(unittest.TestCase):
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

            score = score_site_lead(strong_site_inputs())
            replace_score(connection, lead_id, score)

            row = score_for_lead(connection, lead_id)
            self.assertIsNotNone(row)
            self.assertEqual(int(row["final_score"]), score.final_score)
            self.assertEqual(row["priority_label"], score.priority_label)
            self.assertEqual(int(row["contactability_score"]), score.dimension_scores["contactability"])
            self.assertEqual(row["top_positive_reasons"], score.top_positive_reasons)
            self.assertEqual(row["dimension_reasons"], score.dimension_reasons)

            by_lead = scores_by_lead(connection)
            self.assertIn(lead_id, by_lead)
            for_run = scores_for_run(connection, run_id)
            self.assertEqual(len(for_run), 1)
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

            replace_score(connection, lead_id, score_site_lead(strong_site_inputs()))
            replace_score(connection, lead_id, score_site_lead(strong_site_inputs()))

            count = connection.execute(
                "SELECT COUNT(*) FROM lead_scores WHERE lead_id = ?", (lead_id,)
            ).fetchone()[0]
            self.assertEqual(count, 1)
        finally:
            connection.close()

    def test_score_removed_when_lead_deleted(self) -> None:
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
            replace_score(connection, lead_id, score_site_lead(strong_site_inputs()))

            connection.execute("DELETE FROM leads WHERE id = ?", (lead_id,))
            connection.commit()
            remaining = connection.execute(
                "SELECT COUNT(*) FROM lead_scores WHERE lead_id = ?", (lead_id,)
            ).fetchone()[0]
            self.assertEqual(remaining, 0)
        finally:
            connection.close()
