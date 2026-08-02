import unittest

from src.visual.base import VisualPageReport, VisualSignal
from src.visual.config import VisualConfig
from src.visual.report import (
    PageEntry,
    build_report,
    csv_fields,
    csv_fields_from_row,
    merge_page_entries,
    to_llm_text,
)
from src.visual.signals import (
    SIGNAL_CLUTTER,
    SIGNAL_MODERN,
    SIGNAL_STRONG_BRAND,
    SIGNAL_WEAK_CTA,
    SIGNAL_WEAK_MOBILE,
)

CONFIG = VisualConfig()


def _vsig(name: str, kind: str = "issue") -> VisualSignal:
    return VisualSignal(name=name, detail=name, kind=kind, confidence="medium",
                        weight=0.6, points=-5.0 if kind == "issue" else 5.0, evidence=())


def _page(url: str, page_type: str = "home", signals=(), **kw) -> VisualPageReport:
    defaults = dict(
        url=url, page_type=page_type, screenshot_available=True,
        mobile_screenshot_available=False, visual_score=80,
        layout_quality=80, readability_quality=80, branding_quality=80,
        mobile_quality=80, conversion_quality=80, confidence=1.0,
        issues=(), strengths=(), evidence={}, signals=tuple(signals),
    )
    defaults.update(kw)
    return VisualPageReport(**defaults)


class TestBuildReport(unittest.TestCase):
    def test_counts_signal_pages(self) -> None:
        pages = [
            _page("https://x.com/", "home", [_vsig(SIGNAL_MODERN, "strength"),
                                             _vsig(SIGNAL_STRONG_BRAND, "strength")]),
            _page("https://x.com/about", "internal", [_vsig(SIGNAL_CLUTTER)]),
            _page("https://x.com/contact", "internal", [_vsig(SIGNAL_WEAK_CTA)],
                  mobile_screenshot_available=True),
        ]
        report = build_report("https://x.com", pages, CONFIG)
        self.assertEqual(report.total_pages_audited, 3)
        self.assertEqual(report.pages_with_modern_design_signal, 1)
        self.assertEqual(report.pages_with_clutter_signal, 1)
        self.assertEqual(report.pages_with_weak_cta_signal, 1)
        self.assertEqual(report.pages_with_strong_brand_signal, 1)
        self.assertEqual(report.pages_with_desktop_screenshot, 3)
        self.assertEqual(report.pages_with_mobile_screenshot, 1)

    def test_home_ordered_first(self) -> None:
        pages = [_page("https://x.com/about", "internal"), _page("https://x.com/", "home")]
        report = build_report("https://x.com", pages, CONFIG)
        self.assertEqual(report.pages[0].page_type, "home")

    def test_score_and_label(self) -> None:
        report = build_report("https://x.com", [_page("u", "home", visual_score=72)], CONFIG)
        self.assertEqual(report.visual_score, 72)
        self.assertEqual(report.visual_health_label, "Good")

    def test_llm_result_overrides_template(self) -> None:
        report = build_report(
            "u", [_page("u", "home")], CONFIG,
            llm_result={"summary": "LLM said X", "issues": ["issue1"], "strengths": ["strength1"]},
        )
        self.assertEqual(report.summary, "LLM said X")
        self.assertEqual(report.llm_summary, "LLM said X")

    def test_empty_pages_report(self) -> None:
        report = build_report("u", [], CONFIG)
        self.assertEqual(report.total_pages_audited, 0)
        self.assertEqual(report.visual_score, 100)

    def test_to_dict_is_json_serializable(self) -> None:
        report = build_report("u", [_page("u", "home")], CONFIG)
        d = report.to_dict()
        self.assertIn("visual_score", d)
        self.assertIsInstance(d["pages"], list)


class TestToLlmText(unittest.TestCase):
    def test_empty_report_message(self) -> None:
        text = to_llm_text(build_report("u", [], CONFIG))
        self.assertIn("not available", text)

    def test_includes_score_and_signals(self) -> None:
        report = build_report("u", [_page("u", "home", [_vsig(SIGNAL_CLUTTER)])], CONFIG)
        text = to_llm_text(report)
        self.assertIn("visual audit", text)
        self.assertIn("cluttered", text.lower())


class TestCsvFields(unittest.TestCase):
    def test_csv_fields_keys(self) -> None:
        report = build_report("u", [_page("u", "home", [_vsig(SIGNAL_WEAK_MOBILE)])], CONFIG)
        fields = csv_fields(report)
        for key in ("visual_score", "visual_health_label", "visual_summary",
                    "pages_with_weak_mobile_signal", "pages_with_clutter_signal"):
            self.assertIn(key, fields)
        self.assertEqual(fields["pages_with_weak_mobile_signal"], 1)

    def test_csv_fields_from_row(self) -> None:
        row = {
            "visual_score": 55, "visual_health_label": "Fair", "summary": "ok",
            "pages_with_weak_mobile_signal": 2, "pages_with_clutter_signal": 1,
            "pages_with_weak_cta_signal": 0, "pages_with_strong_brand_signal": 0,
            "pages_with_weak_hierarchy_signal": 0,
        }
        fields = csv_fields_from_row(row)
        self.assertEqual(fields["visual_score"], 55)
        self.assertEqual(fields["pages_with_weak_mobile_signal"], 2)


class TestMergePageEntries(unittest.TestCase):
    def test_desktop_and_mobile_merge(self) -> None:
        entries = [
            PageEntry(url="u", page_type="home", variant="desktop",
                      screenshot_path="d.png", screenshot_hash="h",
                      signals=(_vsig(SIGNAL_MODERN, "strength"),), score=90,
                      subscores={"layout_quality": 90}, confidence=2.0),
            PageEntry(url="u", page_type="home", variant="mobile",
                      screenshot_path="m.png", screenshot_hash="h2",
                      signals=(_vsig(SIGNAL_WEAK_MOBILE),), score=60,
                      subscores={"layout_quality": 60}, confidence=1.0),
        ]
        page = merge_page_entries(entries)
        self.assertTrue(page.screenshot_available)
        self.assertTrue(page.mobile_screenshot_available)
        self.assertEqual(page.screenshot_path, "d.png")
        self.assertEqual(page.mobile_screenshot_path, "m.png")

    def test_desktop_only(self) -> None:
        entries = [PageEntry(url="u", page_type="home", variant="desktop",
                             screenshot_path="d.png", screenshot_hash="h",
                             signals=(), score=80, subscores={}, confidence=1.0)]
        page = merge_page_entries(entries)
        self.assertTrue(page.screenshot_available)
        self.assertFalse(page.mobile_screenshot_available)


if __name__ == "__main__":
    unittest.main()

