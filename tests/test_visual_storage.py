import os
import tempfile
import unittest
from pathlib import Path

from src.storage.db import connect, init_db
from src.storage.leads import LeadUpsert, upsert_lead
from src.storage.normalization import normalize_url_for_dedupe
from src.storage.runs import start_run
from src.storage.technologies import get_lead_id_by_url
from src.storage.visual import (
    audits_by_lead,
    audits_for_run,
    page_audits_for_audit,
    replace_visual_audit,
)
from src.visual.base import VisualPageReport
from src.visual.config import VisualConfig
from src.visual.report import build_report

CONFIG = VisualConfig()


def _page(url: str, page_type: str = "home") -> VisualPageReport:
    return VisualPageReport(
        url=url, page_type=page_type, screenshot_available=True,
        mobile_screenshot_available=False, visual_score=75,
        layout_quality=70, readability_quality=80, branding_quality=75,
        mobile_quality=85, conversion_quality=60, confidence=1.0,
        issues=("cluttered layout",), strengths=("modern design",),
        evidence={"ink_ratio": 0.3}, signals=(),
    )


class TestVisualStorage(unittest.TestCase):
    def setUp(self) -> None:
        self._db = tempfile.mktemp(suffix=".sqlite")
        self.conn = connect(Path(self._db))
        init_db(self.conn)
        self.run_id = start_run(self.conn)
        upsert_lead(self.conn, LeadUpsert(
            website_url="https://x.com", business_name="X",
            run_id=self.run_id, extraction_success=True,
        ))
        self.lead_id = get_lead_id_by_url(self.conn, normalize_url_for_dedupe("https://x.com"))
        assert self.lead_id is not None

    def tearDown(self) -> None:
        self.conn.close()
        if os.path.exists(self._db):
            os.unlink(self._db)

    def _persist(self, n_pages: int = 1) -> int:
        pages = [_page("https://x.com/", "home")]
        if n_pages > 1:
            pages.append(_page("https://x.com/about", "internal"))
        report = build_report("https://x.com", pages, CONFIG)
        site = report.to_dict()
        page_dicts = site.pop("pages")
        return replace_visual_audit(self.conn, self.lead_id, site, page_dicts)

    def test_round_trip(self) -> None:
        audit_id = self._persist()
        self.assertGreater(audit_id, 0)
        rows = audits_for_run(self.conn, self.run_id)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["visual_score"], 75)
        self.assertEqual(rows[0]["visual_health_label"], "Good")

    def test_replace_is_idempotent(self) -> None:
        self._persist()
        self._persist()
        rows = audits_for_run(self.conn, self.run_id)
        self.assertEqual(len(rows), 1)

    def test_page_rows_and_json_decode(self) -> None:
        audit_id = self._persist(n_pages=2)
        page_rows = page_audits_for_audit(self.conn, audit_id)
        self.assertEqual(len(page_rows), 2)
        self.assertIsInstance(page_rows[0]["issues"], list)
        self.assertIsInstance(page_rows[0]["strengths"], list)

    def test_audits_by_lead(self) -> None:
        self._persist()
        by_lead = audits_by_lead(self.conn)
        self.assertIn(self.lead_id, by_lead)
        self.assertEqual(by_lead[self.lead_id]["visual_score"], 75)


if __name__ == "__main__":
    unittest.main()
