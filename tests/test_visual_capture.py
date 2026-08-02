import asyncio
import tempfile
import unittest
from pathlib import Path

from src.scraping.browser_fetch import ScreenshotResult
from src.visual.base import PAGE_TYPE_HOME, VARIANT_DESKTOP, VARIANT_MOBILE
from src.visual.capture import (
    CaptureJob,
    build_ref,
    capture_for_lead,
    lead_screenshot_dir,
    normalize_capture_url,
    plan_captures,
    screenshot_metadata,
)

from tests.visual_fixtures import (
    FakeScreenshoter,
    crawl_pages,
    modern_clean_image,
    solid_image,
    test_config,
)

HOME = "https://example.com"


class TestNormalizeCaptureUrl(unittest.TestCase):
    def test_lowercases_scheme_and_host(self) -> None:
        self.assertEqual(normalize_capture_url("HTTPS://Example.com/About/"), "https://example.com/About")

    def test_drops_fragment(self) -> None:
        self.assertEqual(normalize_capture_url("https://x.com/page#frag"), "https://x.com/page")

    def test_empty_is_empty(self) -> None:
        self.assertEqual(normalize_capture_url(""), "")


class TestLeadScreenshotDir(unittest.TestCase):
    def test_deterministic_hash_dir(self) -> None:
        cfg = test_config()
        d1 = lead_screenshot_dir(cfg, HOME)
        d2 = lead_screenshot_dir(cfg, HOME)
        self.assertEqual(d1, d2)
        self.assertTrue(d1.parent == cfg.screenshot_dir)

    def test_different_urls_different_dirs(self) -> None:
        cfg = test_config()
        self.assertNotEqual(lead_screenshot_dir(cfg, HOME), lead_screenshot_dir(cfg, "https://other.com"))


class TestPlanCaptures(unittest.TestCase):
    def test_home_gets_desktop_and_mobile(self) -> None:
        cfg = test_config()
        jobs = plan_captures(HOME, crawl_pages(["https://example.com/services"]), cfg)
        self.assertEqual(jobs[0].page_type, PAGE_TYPE_HOME)
        self.assertEqual(jobs[0].variant, VARIANT_DESKTOP)
        self.assertEqual(jobs[1].variant, VARIANT_MOBILE)

    def test_internal_pages_desktop_only(self) -> None:
        cfg = test_config()
        jobs = plan_captures(HOME, crawl_pages(["https://example.com/services"]), cfg)
        internal = [j for j in jobs if j.page_type != PAGE_TYPE_HOME]
        self.assertTrue(all(j.variant == VARIANT_DESKTOP for j in internal))

    def test_respects_max_screenshots(self) -> None:
        cfg = test_config(max_screenshots=3)
        jobs = plan_captures(HOME, crawl_pages(["https://example.com/a", "https://example.com/b"]), cfg)
        self.assertEqual(len(jobs), 3)

    def test_home_excluded_from_internal(self) -> None:
        cfg = test_config()
        jobs = plan_captures(HOME, crawl_pages([HOME]), cfg)
        self.assertEqual(len(jobs), 2)  # home desktop + mobile only

    def test_dedupes_internal_urls(self) -> None:
        cfg = test_config()
        jobs = plan_captures(HOME, crawl_pages(["https://example.com/a", "https://example.com/a"]), cfg)
        self.assertEqual(len(jobs), 3)  # home x2 + one internal


class TestScreenshotMetadataAndRef(unittest.TestCase):
    def setUp(self) -> None:
        self._dir = tempfile.mkdtemp(prefix="cap_")

    def test_screenshot_metadata(self) -> None:
        path = Path(self._dir) / "s.png"
        solid_image((0, 0, 0))(str(path))
        meta = screenshot_metadata(path)
        assert meta is not None
        self.assertIn("screenshot_hash", meta)
        self.assertGreater(meta["file_size"], 0)

    def test_screenshot_metadata_missing(self) -> None:
        self.assertIsNone(screenshot_metadata(Path(self._dir) / "nope.png"))

    def test_build_ref_from_result(self) -> None:
        path = Path(self._dir) / "r.png"
        solid_image((0, 0, 0))(str(path))
        job = CaptureJob(HOME, PAGE_TYPE_HOME, VARIANT_DESKTOP, 1365, 900)
        result = ScreenshotResult(url=HOME, final_url=HOME, width=1365, height=900,
                                  full_page=True, probe={"cta_count": 2})
        ref = build_ref(job, result, path, test_config())
        assert ref is not None
        self.assertEqual(ref.url, HOME)
        self.assertEqual(ref.variant, VARIANT_DESKTOP)
        self.assertTrue(ref.screenshot_hash)


class TestCaptureForLead(unittest.TestCase):
    def test_captures_all_planned(self) -> None:
        cfg = test_config()
        fetcher = FakeScreenshoter(
            desktop_image=modern_clean_image(), mobile_image=modern_clean_image(),
        )
        refs = capture_for_lead(fetcher, HOME, crawl_pages(["https://example.com/about"]), cfg)
        self.assertEqual(len(refs), 3)  # home desktop + mobile + about desktop
        for ref in refs:
            self.assertTrue(ref.screenshot_hash)
            self.assertGreater(ref.file_size, 0)

    def test_reuses_existing_screenshots(self) -> None:
        cfg = test_config()
        fetcher = FakeScreenshoter(
            desktop_image=modern_clean_image(), mobile_image=modern_clean_image(),
        )
        capture_for_lead(fetcher, HOME, [], cfg)
        first_count = len(fetcher.captured)
        # Second call should reuse files (no new fetcher calls).
        capture_for_lead(fetcher, HOME, [], cfg)
        self.assertEqual(len(fetcher.captured), first_count)

    def test_failing_urls_skipped(self) -> None:
        cfg = test_config()
        fetcher = FakeScreenshoter(
            desktop_image=modern_clean_image(), mobile_image=modern_clean_image(),
            failing_urls={HOME},
        )
        refs = capture_for_lead(fetcher, HOME, [], cfg)
        self.assertEqual(refs, [])


if __name__ == "__main__":
    unittest.main()
