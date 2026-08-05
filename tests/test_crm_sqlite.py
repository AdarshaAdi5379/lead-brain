"""Unit tests for the CRM fields on the leads table (src/storage/leads.py).

Confirms the additive-migration columns exist and ``update_crm_fields`` behaves.
"""

from __future__ import annotations

import unittest

from tests.search_fixtures import SearchTestDb

from src.storage.leads import update_crm_fields


class UpdateCrmFieldsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.db = SearchTestDb()
        self.lid = self.db.add_lead(name="Taco Stand", website="https://taco.com")

    def tearDown(self) -> None:
        self.db.close()

    def _row(self, lead_id: int) -> dict[str, object]:
        return dict(
            self.db.connection.execute(
                "SELECT status, notes, last_contacted, next_follow_up, assigned_to,"
                " best_contact_method FROM leads WHERE id = ?", (lead_id,)
            ).fetchone()
        )

    def test_columns_exist(self) -> None:
        row = self._row(self.lid)
        self.assertEqual(
            set(row),
            {"status", "notes", "last_contacted", "next_follow_up", "assigned_to",
             "best_contact_method"},
        )
        self.assertIsNone(row["status"])

    def test_sets_non_none_values_only(self) -> None:
        update_crm_fields(
            self.db.connection, self.lid,
            status="Contacted", notes="Hi", assigned_to="Ada",
        )
        row = self._row(self.lid)
        self.assertEqual(row["status"], "Contacted")
        self.assertEqual(row["notes"], "Hi")
        self.assertEqual(row["assigned_to"], "Ada")
        self.assertIsNone(row["last_contacted"])

    def test_none_values_are_skipped(self) -> None:
        update_crm_fields(self.db.connection, self.lid, status="Contacted")
        update_crm_fields(self.db.connection, self.lid, status=None, notes="keep me")
        row = self._row(self.lid)
        self.assertEqual(row["status"], "Contacted")
        self.assertEqual(row["notes"], "keep me")

    def test_missing_lead_is_safe(self) -> None:
        update_crm_fields(self.db.connection, 9999, status="Contacted")  # no raise


if __name__ == "__main__":
    unittest.main()