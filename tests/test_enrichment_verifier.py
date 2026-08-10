"""Page verification: bounded fetches (no real network) and candidate
verification with injected fetchers."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from src.enrichment.base import LeadContext
from src.enrichment.verifier import PageVerification, fetch_page, verify_candidate

from tests.enrichment_fixtures import FakePage, lead, matching_page


class _FakeResponse:
    def __init__(self, body: bytes, content_type: str = "text/html") -> None:
        self._body = body
        self._content_type = content_type

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, size: int = -1) -> bytes:
        if size is None or size < 0:
            return self._body
        return self._body[:size]

    @property
    def headers(self):
        return _Headers(self._content_type)


class _Headers:
    def __init__(self, content_type: str) -> None:
        self._content_type = content_type

    def get(self, name: str, default=None):
        return self._content_type if name.lower() == "content-type" else default


class TestFetchPage(unittest.TestCase):
    def test_html_fetch_ok(self) -> None:
        html = b"<html><head><title>Radiant Plumbing Austin</title></head><body>Radiant Plumbing plumber</body></html>"
        with patch(
            "urllib.request.urlopen", return_value=_FakeResponse(html)
        ) as mock_open:
            page = fetch_page("https://radiantplumbing.com/")
        self.assertTrue(page.ok)
        self.assertEqual(page.title, "Radiant Plumbing Austin")
        self.assertIn("Radiant Plumbing plumber", page.text)
        mock_open.assert_called_once()

    def test_non_html_rejected(self) -> None:
        with patch(
            "urllib.request.urlopen",
            return_value=_FakeResponse(b"not html", content_type="image/png"),
        ):
            page = fetch_page("https://radiantplumbing.com/logo.png")
        self.assertFalse(page.ok)
        self.assertIn("Non-HTML", page.error or "")

    def test_oversized_response_truncated_not_rejected(self) -> None:
        big = b"<html><head><title>Radiant Plumbing Austin</title></head><body>" + b"x" * 400_000 + b"</body></html>"
        with patch("urllib.request.urlopen", return_value=_FakeResponse(big)):
            page = fetch_page("https://radiantplumbing.com/", max_bytes=100_000)
        self.assertTrue(page.ok)
        self.assertEqual(page.title, "Radiant Plumbing Austin")
        self.assertLess(len(page.text), 100_000)

    def test_network_error_fails(self) -> None:
        import urllib.error

        with patch(
            "urllib.request.urlopen",
            side_effect=urllib.error.URLError("connection refused"),
        ):
            page = fetch_page("https://radiantplumbing.com/")
        self.assertFalse(page.ok)
        self.assertIn("connection refused", page.error or "")


class TestVerifyCandidate(unittest.TestCase):
    def test_matching_page_high_score(self) -> None:
        ctx = LeadContext(**lead())
        page, score, signals = verify_candidate(
            "https://radiantplumbing.com/",
            lead=ctx,
            timeout_s=5.0,
            max_bytes=100_000,
            user_agent="test",
            fetcher=lambda url: matching_page(),
        )
        self.assertTrue(page.ok)
        self.assertGreaterEqual(score, 0.75)
        self.assertEqual(signals["brand"], 0.55)

    def test_failed_fetch_never_accepted(self) -> None:
        ctx = LeadContext(**lead())
        page, score, signals = verify_candidate(
            "https://radiantplumbing.com/",
            lead=ctx,
            timeout_s=5.0,
            max_bytes=100_000,
            user_agent="test",
            fetcher=lambda url: FakePage(ok=False, error="timeout"),
        )
        self.assertFalse(page.ok)
        self.assertEqual(score, 0.0)
        self.assertEqual(signals, {})


if __name__ == "__main__":
    unittest.main()