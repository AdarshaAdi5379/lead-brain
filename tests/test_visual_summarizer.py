import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.visual.capture import CaptureJob, build_ref
from src.visual.config import VisualConfig
from src.visual.summarizer import _extract_result, summarize_visual
from src.scraping.browser_fetch import ScreenshotResult

from src.visual.base import PAGE_TYPE_HOME, VARIANT_DESKTOP
from tests.visual_fixtures import solid_image, test_config

HOME = "https://example.com"


def _ref(path: str):
    job = CaptureJob(HOME, PAGE_TYPE_HOME, VARIANT_DESKTOP, 1365, 900)
    result = ScreenshotResult(url=HOME, final_url=HOME, width=1365, height=900,
                              full_page=True, probe={})
    ref = build_ref(job, result, Path(path), test_config())
    assert ref is not None
    return ref


class TestSummarizeVisual(unittest.TestCase):
    def setUp(self) -> None:
        self._dir = tempfile.mkdtemp(prefix="summ_")
        self._img = str(Path(self._dir) / "home.png")
        solid_image((10, 20, 30))(self._img)

    def test_gated_off_returns_none(self) -> None:
        cfg = test_config(llm_enabled=False)
        self.assertIsNone(summarize_visual([_ref(self._img)], cfg))

    def test_mock_returns_structured_result(self) -> None:
        cfg = test_config(llm_enabled=True)
        payload = {"summary": "Clean modern site", "issues": ["thin footer"], "strengths": ["good nav"]}
        with patch("src.llm.openai_responses.create_vision_response", return_value=payload):
            result = summarize_visual([_ref(self._img)], cfg)
        self.assertIsInstance(result, dict)
        assert isinstance(result, dict)
        self.assertEqual(result["summary"], "Clean modern site")
        self.assertIn("thin footer", result["issues"])
        self.assertIn("good nav", result["strengths"])

    def test_mock_failure_returns_none(self) -> None:
        cfg = test_config(llm_enabled=True)
        with patch("src.llm.openai_responses.create_vision_response", side_effect=RuntimeError("boom")):
            self.assertIsNone(summarize_visual([_ref(self._img)], cfg))

    def test_no_homepage_images_returns_none(self) -> None:
        cfg = test_config(llm_enabled=True)
        # Non-existent path -> image can't be loaded -> no images picked.
        ref = _ref(self._img)
        ref = type(ref)(url=ref.url, page_type=ref.page_type, variant=ref.variant,
                        path="/nonexistent/x.png", width=ref.width, height=ref.height,
                        full_page=ref.full_page, probe=ref.probe,
                        screenshot_hash=ref.screenshot_hash, file_size=ref.file_size)
        self.assertIsNone(summarize_visual([ref], cfg))


class TestExtractResult(unittest.TestCase):
    def test_dict_with_summary(self) -> None:
        result = _extract_result({"summary": "ok", "issues": [], "strengths": []})
        self.assertEqual(result["summary"], "ok")
        self.assertEqual(result["issues"], [])

    def test_dict_without_summary(self) -> None:
        self.assertIsNone(_extract_result({"issues": []}))

    def test_keeps_issues_and_strengths(self) -> None:
        result = _extract_result({"summary": "ok", "issues": ["a", 2, None], "strengths": ["s"]})
        assert result is not None
        self.assertEqual(result["issues"], ["a", "2"])
        self.assertEqual(result["strengths"], ["s"])

    def test_non_dict(self) -> None:
        self.assertIsNone(_extract_result("not a dict"))
        self.assertIsNone(_extract_result(None))


if __name__ == "__main__":
    unittest.main()
