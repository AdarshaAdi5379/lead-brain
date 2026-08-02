import asyncio
import unittest

from src.visual.config import VisualConfig
from src.visual.engine import run_visual_audit

from tests.visual_fixtures import (
    FakeScreenshoter,
    crawl_pages,
    low_contrast_image,
    modern_clean_image,
    test_config,
)

HOME = "https://example.com"


def _run(fetcher, home=HOME, crawl=None, detections=None, config=None, page_context=None):
    return asyncio.run(run_visual_audit(
        fetcher, home, crawl or [], detections or [], config or test_config(),
        page_context=page_context,
    ))


class TestRunVisualAudit(unittest.TestCase):
    def test_produces_report(self) -> None:
        fetcher = FakeScreenshoter(
            desktop_image=modern_clean_image(), mobile_image=modern_clean_image(),
        )
        report = _run(fetcher, crawl=crawl_pages(["https://example.com/about"]))
        self.assertIsNotNone(report)
        assert report is not None
        self.assertGreater(report.total_pages_audited, 0)
        self.assertGreaterEqual(report.pages_with_desktop_screenshot, 1)
        self.assertTrue(0 <= report.visual_score <= 100)

    def test_disabled_returns_none(self) -> None:
        fetcher = FakeScreenshoter(
            desktop_image=modern_clean_image(), mobile_image=modern_clean_image(),
        )
        self.assertIsNone(_run(fetcher, config=test_config(enabled=False)))

    def test_all_failures_returns_none(self) -> None:
        fetcher = FakeScreenshoter(
            desktop_image=modern_clean_image(), mobile_image=modern_clean_image(),
            failing_urls={HOME, "https://example.com/about"},
        )
        self.assertIsNone(_run(fetcher, crawl=crawl_pages(["https://example.com/about"])))

    def test_llm_summary_gated_off_by_default(self) -> None:
        fetcher = FakeScreenshoter(
            desktop_image=modern_clean_image(), mobile_image=modern_clean_image(),
        )
        report = _run(fetcher)
        assert report is not None
        self.assertIsNone(report.llm_summary)

    def test_multiple_pages_audited(self) -> None:
        fetcher = FakeScreenshoter(
            desktop_image=modern_clean_image(), mobile_image=modern_clean_image(),
        )
        report = _run(fetcher, crawl=crawl_pages([
            "https://example.com/about", "https://example.com/services",
        ]))
        assert report is not None
        self.assertGreaterEqual(report.total_pages_audited, 2)

    def test_weak_site_scores_lower_than_strong(self) -> None:
        weak = FakeScreenshoter(desktop_image=low_contrast_image(), mobile_image=low_contrast_image())
        strong = FakeScreenshoter(desktop_image=modern_clean_image(), mobile_image=modern_clean_image())
        weak_report = _run(weak, config=test_config())
        strong_report = _run(strong, config=test_config())
        assert weak_report is not None and strong_report is not None
        self.assertLessEqual(weak_report.visual_score, strong_report.visual_score)


    def test_page_context_accepted(self) -> None:
        fetcher = FakeScreenshoter(
            desktop_image=modern_clean_image(), mobile_image=modern_clean_image(),
        )
        report = _run(
            fetcher, crawl=crawl_pages(["https://example.com/about"]),
            page_context={HOME: {"word_count": 1200, "image_count": 0}},
        )
        self.assertIsNotNone(report)
        assert report is not None
        self.assertGreater(report.total_pages_audited, 0)
        self.assertTrue(0 <= report.visual_score <= 100)


if __name__ == "__main__":
    unittest.main()
