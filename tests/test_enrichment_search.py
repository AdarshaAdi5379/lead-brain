"""Free web search: query building and anonymous HTML parsing (no network)."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from src.enrichment.base import LeadContext
from src.enrichment.config import EnrichmentConfig
from src.enrichment.search import (
    _decode_result_href,
    _parse_results,
    build_search_query,
    search_web,
)

from tests.enrichment_fixtures import DDG_RESULTS_HTML, lead


def _ctx(**overrides) -> LeadContext:
    return LeadContext(**lead(**overrides))


class TestBuildSearchQuery(unittest.TestCase):
    def test_name_location_category(self) -> None:
        self.assertEqual(
            build_search_query(_ctx()),
            "Radiant Plumbing Austin TX plumber",
        )

    def test_missing_parts_tolerated(self) -> None:
        self.assertEqual(
            build_search_query(_ctx(city=None, state=None, category=None)),
            "Radiant Plumbing",
        )


class TestDecodeResultHref(unittest.TestCase):
    def test_uddg_wrapper_unwrapped(self) -> None:
        href = "//duckduckgo.com/l/?uddg=https%3A%2F%2Fradiantplumbing.com%2F&rut=abc"
        self.assertEqual(
            _decode_result_href(href),
            "https://radiantplumbing.com/",
        )

    def test_plain_href_passthrough(self) -> None:
        self.assertEqual(_decode_result_href("https://radiantplumbing.com/contact"), "https://radiantplumbing.com/contact")


class TestParseResults(unittest.TestCase):
    def test_organic_results_cleaned_and_deduplicated(self) -> None:
        urls = _parse_results(DDG_RESULTS_HTML)
        self.assertIn("https://radiantplumbing.com/", urls)
        self.assertIn("https://radiantplumbing.com/contact", urls)
        self.assertNotIn("https://www.yelp.com/biz/radiant-plumbing-austin", urls)
        self.assertNotIn("https://www.facebook.com/radiantplumbing", urls)
        # Tracking params stripped; duplicates collapsed.
        self.assertEqual(len(urls), 2)

    def test_empty_page(self) -> None:
        self.assertEqual(_parse_results("<html><body></body></html>"), [])


class TestSearchWeb(unittest.TestCase):
    def test_returns_capped_results(self) -> None:
        html = """
        <html><body>
        <a class="result__a" href="https://a.com">A</a>
        <a class="result__a" href="https://b.com">B</a>
        <a class="result__a" href="https://c.com">C</a>
        <a class="result__a" href="https://d.com">D</a>
        </body></html>
        """
        config = EnrichmentConfig(max_search_results=2)

        class FakeResp:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self, size: int = -1):
                return html.encode()

        with patch("urllib.request.urlopen", return_value=FakeResp()) as mock_open:
            results = search_web("Radiant Plumbing Austin TX", config)
        self.assertEqual(results, ["https://a.com", "https://b.com"])
        mock_open.assert_called_once()


if __name__ == "__main__":
    unittest.main()