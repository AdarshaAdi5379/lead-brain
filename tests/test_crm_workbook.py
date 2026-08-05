"""Unit tests for the Excel CRM workbook IO + validation layer (src/crm/workbook.py).

Pure xlsx behaviour: creation, writing/reading, backups, and cell validation.
SQLite is never touched here (see test_crm_sync.py / test_crm_service.py).
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tests.search_fixtures import SearchTestDb

try:
    from src.crm.columns import COLUMNS, DATE_COLUMNS, URL_COLUMNS
    from src.crm.workbook import (
        create_workbook,
        normalise_row,
        openpyxl_available,
        read_workbook,
        validate_row,
        write_workbook,
    )
except Exception:  # pragma: no cover
    openpyxl_available = lambda: False  # type: ignore

    def _unavailable():
        raise unittest.SkipTest("openpyxl not installed")

    class _Skip:
        def __getattr__(self, name):
            return _unavailable

    COLUMNS = DATE_COLUMNS = URL_COLUMNS = ()
    create_workbook = write_workbook = read_workbook = normalise_row = validate_row = _Skip()


@unittest.skipUnless(openpyxl_available(), "openpyxl not installed")
class WorkbookIOTest(unittest.TestCase):
    def _tmp_path(self) -> Path:
        return Path(tempfile.mktemp(suffix=".xlsx"))

    def _row(self, lead_id: int = 1, **overrides: object) -> dict[str, object]:
        row = {column: None for column in COLUMNS}
        row["lead_id"] = lead_id
        row["business_name"] = "Taco Stand"
        row.update(overrides)
        return row

    def setUp(self) -> None:
        self.db = SearchTestDb()

    def tearDown(self) -> None:
        self.db.close()

    def test_create_writes_canonical_columns(self) -> None:
        path = self._tmp_path()
        rows = [self._row(1, status="New")]
        create_workbook(path, rows)
        self.assertTrue(path.exists())
        loaded = read_workbook(path)
        self.assertEqual(len(loaded), 1)
        self.assertEqual(list(loaded[0].keys()), list(COLUMNS))
        self.assertEqual(loaded[0]["lead_id"], 1)
        self.assertEqual(loaded[0]["status"], "New")

    def test_write_backs_up_existing_file(self) -> None:
        path = self._tmp_path()
        create_workbook(path, [self._row(1, notes="first")])
        write_workbook(path, [self._row(1, notes="second")])
        self.assertTrue(path.with_suffix(".bak.xlsx").exists())
        self.assertIn("second", str(read_workbook(path)[0]["notes"]))

    def test_read_missing_returns_none(self) -> None:
        self.assertIsNone(read_workbook(self._tmp_path()))

    def test_blank_rows_skipped_on_read(self) -> None:
        path = self._tmp_path()
        create_workbook(path, [self._row(1)])
        loaded = read_workbook(path)
        self.assertEqual(len(loaded), 1)

    def test_validate_requires_known_lead_id(self) -> None:
        ok, issues = validate_row(self._row(99), known_lead_ids={1})
        self.assertFalse(ok)
        self.assertTrue(any("lead_id" in issue for issue in issues))

    def test_validate_rejects_bad_url_accepts_http_and_https(self) -> None:
        bad = self._row(website_url="ftp://taco.com", facebook_url="taco")
        ok, issues = validate_row(bad, known_lead_ids={1})
        self.assertTrue(any("website_url" in iss for iss in issues))
        self.assertTrue(any("facebook_url" in iss for iss in issues))
        good = self._row(website_url="http://taco.com", facebook_url="https://fb.com/taco")
        ok, issues = validate_row(good, known_lead_ids={1})
        self.assertTrue(ok)
        self.assertEqual(issues, [])

    def test_validate_rejects_bad_date_accepts_iso(self) -> None:
        bad = self._row(last_contacted="10/08/2026")
        ok, issues = validate_row(bad, known_lead_ids={1})
        self.assertFalse(ok)
        self.assertTrue(any("last_contacted" in iss for iss in issues))
        good = self._row(last_contacted="2026-08-10", next_follow_up="2026-08-20")
        ok, issues = validate_row(good, known_lead_ids={1})
        self.assertTrue(ok)

    def test_normalise_blank_stays_empty_and_junk_cleared(self) -> None:
        row = self._row(
            business_name="  ",
            website_url="not a url",
            last_contacted="bad date",
            status=" New ",
        )
        cleaned = normalise_row(row)
        self.assertIsNone(cleaned["business_name"])
        self.assertIsNone(cleaned["website_url"])
        self.assertIsNone(cleaned["last_contacted"])
        self.assertEqual(cleaned["status"], "New")


if __name__ == "__main__":
    unittest.main()