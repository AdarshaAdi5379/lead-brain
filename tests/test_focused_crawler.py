import asyncio
import tempfile
import unittest
from pathlib import Path

from src.scraping.browser_fetch import FetchResult
from src.scraping.focused_crawler import FocusedCrawler
from src.scraping.page_cache import PageCache

HOME = "https://acme.example.com/"


def _article_html(title: str, paras: list[str] | None = None) -> str:
    body = "".join(f"<p>{p}</p>" for p in (paras or [f"text from {title} page."]))
    return f"<html><head><title>{title}</title></head><body>{body}</body></html>"


HOMEPAGE = """<html><head><title>Acme Plumbing</title></head><body>
<h1>Acme Plumbing</h1>
<p>We fix pipes and water heaters in Austin, TX.</p>
<nav>
  <a href="/about">About Us</a>
  <a href="/services">Our Services</a>
  <a href="/portfolio">Portfolio</a>
  <a href="/contact">Contact</a>
  <a href="/privacy">Privacy</a>
  <a href="https://other.example.com/">External</a>
  <a href="mailto:hello@acme.example.com">Email</a>
  <a href="/">Home link</a>
</nav>
</body></html>"""

PAGES = {
    "https://acme.example.com/about": _article_html("About", ["Since 1990, family owned."]),
    "https://acme.example.com/services": _article_html(
        "Services", ["Emergency repairs, installations, and maintenance."]
    ),
    "https://acme.example.com/portfolio": _article_html(
        "Portfolio", ["See recent commercial and residential jobs."]
    ),
    "https://acme.example.com/contact": _article_html(
        "Contact", ["Call 512-555-0100 or email info@acme.example.com."]
    ),
    "https://acme.example.com/privacy": _article_html("Privacy", ["We never sell your data."]),
}


def _site() -> dict[str, str]:
    return dict(PAGES, **{HOME: HOMEPAGE})


class FakeFetcher:
    def __init__(self, pages: dict[str, str]) -> None:
        self._pages = pages
        self.calls: list[str] = []

    async def fetch(self, url: str) -> FetchResult:
        self.calls.append(url)
        html = self._pages.get(url)
        if html is None:
            return FetchResult(
                url=url,
                final_url=None,
                success=False,
                status=404,
                html=None,
                text=None,
                error="HTTP 404",
            )
        return FetchResult(
            url=url,
            final_url=None,
            success=True,
            status=200,
            html=html,
            text=html,
            error=None,
        )


def _crawl(crawler: FocusedCrawler, fetcher: FakeFetcher):
    return asyncio.run(crawler.crawl(fetcher, HOME))


class TestFocusedCrawler(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._cache = PageCache(Path(self._tmp.name), "pages.json")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _crawler(self, max_pages: int = 5) -> FocusedCrawler:
        return FocusedCrawler(max_pages=max_pages, cache=self._cache)

    def test_home_and_ranked_pages_merged(self) -> None:
        result = _crawl(self._crawler(), FakeFetcher(_site()))
        self.assertTrue(result.ok)
        merged = result.merged_text
        for label in ("HOME", "About Us", "Our Services", "Portfolio", "Contact", "CONTACT"):
            self.assertIn(label, merged)
        self.assertIn("family owned", merged)
        self.assertIn("water heaters", merged)
        self.assertIn("info@acme.example.com", merged)

    def test_homepage_failure_returns_invalid_crawl(self) -> None:
        result = _crawl(self._crawler(), FakeFetcher({}))
        self.assertFalse(result.ok)
        self.assertEqual(result.merged_text, "")
        self.assertIsNone(result.metadata)

    def test_budget_respected(self) -> None:
        result = _crawl(self._crawler(max_pages=5), FakeFetcher(_site()))
        self.assertTrue(result.ok)
        self.assertLessEqual(result.metadata.visited_pages, 5)
        self.assertLessEqual(len(result.pages), 5)
        self.assertGreaterEqual(result.metadata.selected_pages, 3)

    def test_page_failure_does_not_abort(self) -> None:
        site = _site()
        del site["https://acme.example.com/services"]
        result = _crawl(self._crawler(), FakeFetcher(site))
        self.assertTrue(result.ok)
        self.assertGreaterEqual(result.metadata.failed_pages, 1)
        self.assertIn("About Us", result.merged_text)
        self.assertIn("Portfolio", result.merged_text)

    def test_page_cache_reuse_across_runs(self) -> None:
        crawler = self._crawler()
        first = _crawl(crawler, FakeFetcher(_site()))
        self.assertGreater(len(first.pages), 1)

        # Second run homepage fetch only; ranked pages come from the cache.
        fetcher2 = FakeFetcher({HOME: HOMEPAGE})
        second = _crawl(crawler, fetcher2)
        self.assertGreater(second.metadata.cached_pages, 0)
        self.assertEqual(len(fetcher2.calls), 1)
        self.assertEqual(len(second.pages), len(first.pages))

    def test_content_hash_is_deterministic(self) -> None:
        first = _crawl(self._crawler(), FakeFetcher(_site()))
        second = _crawl(self._crawler(), FakeFetcher(_site()))
        self.assertEqual(first.content_hash, second.content_hash)

    def test_contact_page_crawled_first(self) -> None:
        fetcher = FakeFetcher(_site())
        result = _crawl(self._crawler(), fetcher)
        self.assertTrue(result.ok)
        self.assertEqual(fetcher.calls[0], HOME)
        self.assertEqual(fetcher.calls[1], "https://acme.example.com/contact")
        self.assertIn("/contact", result.contact_signals.contact_page_url)

    def test_contact_page_kept_when_budget_tight(self) -> None:
        fetcher = FakeFetcher(_site())
        result = _crawl(self._crawler(max_pages=2), fetcher)
        self.assertTrue(result.ok)
        self.assertLessEqual(result.metadata.visited_pages, 2)
        labels = [page.label for page in result.pages]
        self.assertIn("Contact", labels)
        self.assertIn("Call 512-555-0100", result.merged_text)

    def test_contact_signals_attached_from_raw_html(self) -> None:
        from tests.contact_fixtures import JSONLD_HOMEPAGE

        site = dict(PAGES, **{HOME: JSONLD_HOMEPAGE})
        result = _crawl(self._crawler(), FakeFetcher(site))
        self.assertTrue(result.ok)
        signals = result.contact_signals
        self.assertEqual(signals.postal_code, "78701")
        self.assertEqual(signals.facebook_url, "https://www.facebook.com/acmeplumbing")
        self.assertEqual(signals.twitter_url, "https://x.com/acmeplumbing")
        self.assertIsNotNone(signals.contact_page_url)
        self.assertIn("/contact", signals.contact_page_url)
        self.assertTrue(all(p.contact is not None for p in result.pages))

    def test_contact_signals_survive_cache_reuse(self) -> None:
        from tests.contact_fixtures import JSONLD_HOMEPAGE

        site = dict(PAGES, **{HOME: JSONLD_HOMEPAGE})
        crawler = self._crawler()
        first = _crawl(crawler, FakeFetcher(site))
        self.assertIsNotNone(first.contact_signals.facebook_url)

        # Second run: only the homepage is fetched; ranked pages come from cache.
        fetcher2 = FakeFetcher({HOME: JSONLD_HOMEPAGE})
        second = _crawl(crawler, fetcher2)
        self.assertGreater(second.metadata.cached_pages, 0)
        self.assertEqual(len(fetcher2.calls), 1)
        self.assertTrue(all(p.contact is not None for p in second.pages))
        self.assertEqual(second.contact_signals.facebook_url, first.contact_signals.facebook_url)


if __name__ == "__main__":
    unittest.main()