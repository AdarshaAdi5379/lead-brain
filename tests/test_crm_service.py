"""Integration tests for the CRM facade (src/crm/service.py).

Full loop: sync a temp workbook from SQLite, edit, save, reload, and verify both
the workbook and SQLite reflect the change. Also covers the dashboard data path.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import Any

from tests.search_fixtures import SearchTestDb
from src.crm.columns import COLUMNS, DEFAULT_STATUS, MANUAL_COLUMNS
from src.crm.service import CrmService
from src.crm.workbook import openpyxl_available
from src.storage.search import lead_intelligence

try:
    import pandas as pd  # type: ignore
except Exception:  # pragma: no cover
    pd = None


@unittest.skipUnless(openpyxl_available(), "openpyxl not installed")
class CrmServiceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.db = SearchTestDb()
        self.lid = self.db.add_lead(name="Taco Stand", website="https://taco.com",
                                    category="Restaurant", city="Austin")
        self.db.add_contact(self.lid, email="joy@taco.com", phone="512-555-0100")
        self.db.add_score(self.lid, final_score=74, priority_label="Warm")
        self.wb = Path(tempfile.mktemp(suffix=".xlsx"))
        self.service = CrmService(self.db.path, workbook_path=self.wb)

    def tearDown(self) -> None:
        self.db.close()
        for suffix in ("", ".bak.xlsx"):
            path = self.wb if not suffix else self.wb.with_suffix(suffix)
            if path.exists():
                path.unlink()

    def test_sync_creates_workbook_with_default_status(self) -> None:
        rows = self.service.sync()
        self.assertTrue(self.wb.exists())
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["status"], DEFAULT_STATUS)
        self.assertEqual(rows[0]["lead_score"], 74)
        self.assertEqual(rows[0]["email"], "joy@taco.com")

    def test_save_load_round_trip_and_sqlite_write_back(self) -> None:
        rows = self.service.load()
        rows[0]["status"] = "In review"
        rows[0]["notes"] = "Met at the market"
        rows[0]["assigned_to"] = "Me"
        ok, issues = self.service.save(rows)
        self.assertTrue(ok)
        self.assertEqual(issues, [])
        loaded = self.service.load()
        self.assertEqual(loaded[0]["status"], "In review")
        self.assertEqual(loaded[0]["notes"], "Met at the market")
        lead = dict(
            self.db.connection.execute(
                "SELECT status, notes, assigned_to FROM leads WHERE id = ?",
                (self.lid,),
            ).fetchone()
        )
        self.assertEqual(lead["status"], "In review")
        self.assertEqual(lead["notes"], "Met at the market")

    def test_refresh_preserves_manual_edits(self) -> None:
        rows = self.service.load()
        rows[0]["status"] = "Contacted"
        self.service.save(rows)
        refreshed = self.service.sync()  # non-destructive refresh
        self.assertEqual(refreshed[0]["status"], "Contacted")

    def test_rebuild_discards_manual_edits(self) -> None:
        rows = self.service.load()
        rows[0]["status"] = "Contacted"
        self.service.save(rows)
        rebuilt = self.service.rebuild()
        self.assertEqual(rebuilt[0]["status"], DEFAULT_STATUS)

    def test_save_normalises_invalid_cells(self) -> None:
        rows = self.service.load()
        rows[0]["website_url"] = "not a url"
        rows[0]["status"] = "  Chased  "
        ok, issues = self.service.save(rows)
        self.assertTrue(ok)
        self.assertTrue(any("website_url" in i for i in issues))
        loaded = self.service.load()
        self.assertIsNone(loaded[0]["website_url"])
        self.assertEqual(loaded[0]["status"], "Chased")

    def test_columns_and_statistics(self) -> None:
        self.assertEqual(tuple(self.service.columns()), tuple(COLUMNS))
        self.assertEqual(tuple(self.service.manual_columns()), tuple(MANUAL_COLUMNS))
        rows = self.service.load()
        stats = self.service.statistics(rows)
        self.assertEqual(stats["total"], 1)
        self.assertEqual(stats["by_status"].get(DEFAULT_STATUS), 1)

    def test_intel_matches_workbook_row(self) -> None:
        rows = self.service.load()
        intel = lead_intelligence(self.db.connection, lead_id=self.lid)
        self.assertEqual(rows[0]["lead_id"], intel["lead"]["id"])
        self.assertEqual(rows[0]["business_name"], intel["lead"]["business_name"])


@unittest.skipUnless(pd is not None, "pandas not installed")
class CrmDashboardDataPathTest(unittest.TestCase):
    """Exercises the exact helpers the dashboard uses to feed st.data_editor."""

    def setUp(self) -> None:
        self.db = SearchTestDb()
        self.db.add_lead(name="Sushi Bar", website="https://sushi.com", city="Dallas")

    def tearDown(self) -> None:
        self.db.close()

    def test_records_from_editor_df(self) -> None:
        import dashboard
        self.assertIsNotNone(dashboard.CrmService)
        rows = dashboard.CrmService(self.db.path).load()
        frame = pd.DataFrame(rows)
        frame = frame.where(pd.notna(frame), None)
        records = dashboard._crm_records(frame.to_dict("records"))
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["business_name"], "Sushi Bar")
        records2 = dashboard._crm_records(records)
        self.assertEqual(records2, records)


if __name__ == "__main__":
    unittest.main()