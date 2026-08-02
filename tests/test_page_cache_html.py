import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from src.scraping.page_cache import PageCache


class TestPageCacheHtml(unittest.TestCase):
    def test_put_and_get_html_round_trip(self) -> None:
        with TemporaryDirectory() as tmp:
            cache = PageCache(Path(tmp))
            cache.put("https://example.com/a", "cleaned text", html="<html><body>raw</body></html>")
            self.assertEqual(cache.get("https://example.com/a"), "cleaned text")
            self.assertEqual(cache.get_html("https://example.com/a"), "<html><body>raw</body></html>")

    def test_put_without_html_returns_none(self) -> None:
        with TemporaryDirectory() as tmp:
            cache = PageCache(Path(tmp))
            cache.put("https://example.com/a", "cleaned text")
            self.assertIsNone(cache.get_html("https://example.com/a"))
            self.assertEqual(cache.get("https://example.com/a"), "cleaned text")

    def test_legacy_records_without_html_are_tolerated(self) -> None:
        with TemporaryDirectory() as tmp:
            (Path(tmp) / "pages.json").write_text(
                json.dumps({"https://example.com/legacy": {"hash": "h", "text": "old text"}}),
                encoding="utf-8",
            )
            cache = PageCache(Path(tmp))
            self.assertEqual(cache.get("https://example.com/legacy"), "old text")
            self.assertIsNone(cache.get_html("https://example.com/legacy"))

    def test_html_persists_across_cache_reloads(self) -> None:
        with TemporaryDirectory() as tmp:
            cache = PageCache(Path(tmp))
            cache.put("https://example.com/a", "text", html="<p>raw</p>")
            reloaded = PageCache(Path(tmp))
            self.assertEqual(reloaded.get_html("https://example.com/a"), "<p>raw</p>")


if __name__ == "__main__":
    unittest.main()
