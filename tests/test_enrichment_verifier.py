"""Page verification: bounded fetches (no real network) and candidate
verification with injected fetchers."""

from __future__ import annotations

import io
import unittest
import urllib.error
from email.message import Message
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

    def close(self) -> None:
        pass

    def read(self, size: int = -1) -> bytes:
        if size is None or size < 0:
            return self._body
        return self._body[:size]

    @property
    def headers(self):
        return _Headers(self._content_type)


def _redirect_error(code: int, location: str) -> urllib.error.HTTPError:
    headers = Message()
    headers["Location"] = location
    return urllib.error.HTTPError(
        "https://radiantplumbing.com/", code, "Moved", headers, io.BytesIO(b"")
    )


class _Headers:
    def __init__(self, content_type: str) -> None:
        self._content_type = content_type

    def get(self, name: str, default=None):
        return self._content_type if name.lower() == "content-type" else default


class TestFetchPage(unittest.TestCase):
    def test_html_fetch_ok(self) -> None:
        html = b"<html><head><title>Radiant Plumbing Austin</title></head><body>Radiant Plumbing plumber</body></html>"
        with patch(
            "src.enrichment.verifier._open_with_no_redirect", return_value=_FakeResponse(html)
        ) as mock_open:
            page = fetch_page("https://radiantplumbing.com/")
        self.assertTrue(page.ok)
        self.assertEqual(page.title, "Radiant Plumbing Austin")
        self.assertIn("Radiant Plumbing plumber", page.text)
        mock_open.assert_called_once()

    def test_non_html_rejected(self) -> None:
        with patch(
            "src.enrichment.verifier._open_with_no_redirect",
            return_value=_FakeResponse(b"not html", content_type="image/png"),
        ):
            page = fetch_page("https://radiantplumbing.com/logo.png")
        self.assertFalse(page.ok)
        self.assertIn("Non-HTML", page.error or "")

    def test_oversized_response_truncated_not_rejected(self) -> None:
        big = b"<html><head><title>Radiant Plumbing Austin</title></head><body>" + b"x" * 400_000 + b"</body></html>"
        with patch("src.enrichment.verifier._open_with_no_redirect", return_value=_FakeResponse(big)):
            page = fetch_page("https://radiantplumbing.com/", max_bytes=100_000)
        self.assertTrue(page.ok)
        self.assertEqual(page.title, "Radiant Plumbing Austin")
        self.assertLess(len(page.text), 100_000)

    def test_network_error_fails(self) -> None:
        import urllib.error

        with patch(
            "src.enrichment.verifier._open_with_no_redirect",
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


class TestRedirectSecurity(unittest.TestCase):
    """Every redirect hop must pass the trust boundary before it is requested."""

    def _run(self, side_effects) -> tuple[PageVerification, list[str]]:
        requested: list[str] = []

        def opener(request, timeout_s):
            requested.append(request.full_url)
            effect = side_effects.pop(0)
            if isinstance(effect, Exception):
                raise effect
            return effect

        with patch(
            "src.enrichment.verifier._open_with_no_redirect", side_effect=opener
        ):
            page = fetch_page("https://radiantplumbing.com/")
        return page, requested

    _HTML = b"<html><head><title>Final</title></head><body>ok page content</body></html>"

    def test_public_to_public_redirect_followed(self) -> None:
        page, requested = self._run(
            [
                _redirect_error(302, "https://www.radiantplumbing.com/home"),
                _FakeResponse(self._HTML),
            ]
        )
        self.assertTrue(page.ok)
        self.assertEqual(requested, ["https://radiantplumbing.com/", "https://www.radiantplumbing.com/home"])

    def test_multi_hop_public_chain_ok(self) -> None:
        page, requested = self._run(
            [
                _redirect_error(301, "https://a.example.org/"),
                _redirect_error(308, "https://b.example.org/final"),
                _FakeResponse(self._HTML),
            ]
        )
        self.assertTrue(page.ok)
        self.assertEqual(len(requested), 3)

    def test_redirect_to_private_ip_blocked_before_request(self) -> None:
        page, requested = self._run(
            [_redirect_error(302, "http://192.168.1.5/admin")]
        )
        self.assertFalse(page.ok)
        self.assertIn("Unsafe redirect blocked", page.error or "")
        # Only the initial public URL was ever requested.
        self.assertEqual(len(requested), 1)

    def test_redirect_to_localhost_blocked_before_request(self) -> None:
        page, requested = self._run(
            [_redirect_error(302, "http://127.0.0.1:6379/")]
        )
        self.assertFalse(page.ok)
        self.assertIn("Unsafe redirect blocked", page.error or "")
        self.assertEqual(len(requested), 1)

    def test_redirect_to_file_scheme_blocked_before_request(self) -> None:
        page, requested = self._run(
            [_redirect_error(302, "file:///etc/passwd")]
        )
        self.assertFalse(page.ok)
        self.assertIn("Unsafe redirect blocked", page.error or "")
        self.assertEqual(len(requested), 1)

    def test_redirect_to_link_local_metadata_blocked_before_request(self) -> None:
        page, requested = self._run(
            [_redirect_error(301, "http://169.254.169.254/latest/meta-data/")]
        )
        self.assertFalse(page.ok)
        self.assertIn("Unsafe redirect blocked", page.error or "")
        self.assertEqual(len(requested), 1)

    def test_relative_redirect_resolved_and_validated(self) -> None:
        page, requested = self._run(
            [_redirect_error(303, "/contact"), _FakeResponse(self._HTML)]
        )
        self.assertTrue(page.ok)
        self.assertEqual(requested[-1], "https://radiantplumbing.com/contact")

    def test_unsafe_initial_url_never_requested(self) -> None:
        with patch(
            "src.enrichment.verifier._open_with_no_redirect"
        ) as mock_open:
            for bad in ("file:///etc/passwd", "http://169.254.169.254/", "http://127.0.0.1:6379/"):
                with self.subTest(url=bad):
                    page = fetch_page(bad)
                    self.assertFalse(page.ok)
                    self.assertIn("Unsafe URL", page.error or "")
        mock_open.assert_not_called()


class TestVerifyCandidateSecurity(unittest.TestCase):
    def test_unsafe_candidate_rejected_without_fetcher_consultation(self) -> None:
        ctx = LeadContext(**lead())
        consulted: list[str] = []

        def fetcher(url: str) -> FakePage:
            consulted.append(url)
            return matching_page()

        for bad in ("http://127.0.0.1:6379/", "file:///etc/passwd"):
            with self.subTest(url=bad):
                page, score, signals = verify_candidate(
                    bad,
                    lead=ctx,
                    timeout_s=5.0,
                    max_bytes=100_000,
                    user_agent="test",
                    fetcher=fetcher,
                )
                self.assertFalse(page.ok)
                self.assertEqual(score, 0.0)
                self.assertEqual(signals, {})
                self.assertIn("Unsafe URL", page.error or "")
        self.assertEqual(consulted, [])


if __name__ == "__main__":
    unittest.main()