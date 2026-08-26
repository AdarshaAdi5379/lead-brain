# Offline regression suite for the shared URL trust boundary (Phase R1).
from __future__ import annotations

import socket
import unittest

from src.net.url_guard import (
    UnsafeUrlError,
    is_safe_public_http_url,
    validate_public_http_url,
)
from src.scraping.browser_fetch import PlaywrightFetcher, _route_request_allowed


def _resolver(*addresses: str):
    """Injectable resolver returning a fixed address list."""

    def resolve(host: str) -> list[str]:
        return list(addresses)

    return resolve


_PUBLIC_RESOLVER = _resolver("93.184.216.34")


class TestDnsResolution(unittest.TestCase):
    def test_hostname_resolving_to_loopback_rejected(self) -> None:
        with self.assertRaises(UnsafeUrlError):
            validate_public_http_url(
                "http://rebind.example.net/", resolver=_resolver("127.0.0.1")
            )

    def test_hostname_resolving_to_rfc1918_rejected(self) -> None:
        with self.assertRaises(UnsafeUrlError):
            validate_public_http_url(
                "http://rebind.example.net/", resolver=_resolver("10.0.0.1")
            )

    def test_hostname_resolving_to_link_local_rejected(self) -> None:
        with self.assertRaises(UnsafeUrlError):
            validate_public_http_url(
                "http://rebind.example.net/", resolver=_resolver("169.254.169.254")
            )

    def test_mixed_public_and_private_addresses_rejected(self) -> None:
        with self.assertRaises(UnsafeUrlError):
            validate_public_http_url(
                "http://rebind.example.net/",
                resolver=_resolver("93.184.216.34", "10.0.0.2"),
            )

    def test_hostname_resolving_to_public_accepted(self) -> None:
        url = validate_public_http_url(
            "http://example.net/page", resolver=_PUBLIC_RESOLVER
        )
        self.assertEqual(url, "http://example.net/page")

    def test_resolution_failure_passes_through_for_transport_to_fail(self) -> None:
        def failing_resolver(host: str) -> list[str]:
            raise socket.gaierror("temporary dns outage")

        url = "http://unreachable.invalid/"
        self.assertEqual(validate_public_http_url(url, resolver=failing_resolver), url)

    def test_literal_ip_skips_dns(self) -> None:
        def explode(host: str) -> list[str]:
            raise AssertionError("DNS must not be consulted for IP literals")

        with self.assertRaises(UnsafeUrlError):
            validate_public_http_url("http://192.168.0.9/", resolver=explode)

    def test_syntax_only_mode_skips_dns_for_hostnames(self) -> None:
        def explode(host: str) -> list[str]:
            raise AssertionError("DNS must not be consulted with resolve_dns=False")

        self.assertTrue(
            is_safe_public_http_url("https://example.com", resolver=explode, resolve_dns=False)
        )


class TestRouteRequestAllowed(unittest.TestCase):
    """The Playwright routing-layer decision helper."""

    def test_non_network_inline_schemes_allowed_as_subresources(self) -> None:
        cache: dict[str, bool] = {}
        self.assertTrue(_route_request_allowed("data:image/png;base64,AAAA", cache))
        self.assertTrue(_route_request_allowed("about:blank", cache))

    def test_dangerous_schemes_blocked(self) -> None:
        cache: dict[str, bool] = {}
        for bad in (
            "file:///etc/passwd",
            "javascript:void(0)",
            "ftp://example.com/x",
        ):
            with self.subTest(url=bad):
                self.assertFalse(_route_request_allowed(bad, cache))

    def test_private_ip_subresource_blocked(self) -> None:
        cache: dict[str, bool] = {}
        self.assertFalse(_route_request_allowed("http://127.0.0.1:6379/", cache))
        self.assertFalse(_route_request_allowed("http://192.168.1.20/img.png", cache))
        self.assertFalse(_route_request_allowed("http://169.254.169.254/", cache))


class TestPlaywrightFetchBoundary(unittest.TestCase):
    """Unsafe URLs must fail before Chromium (or any context) is touched."""

    def _fetcher(self) -> PlaywrightFetcher:
        fetcher = PlaywrightFetcher()
        # Simulate an active session; the boundary must bail out before the
        # dummy object could ever be used.
        fetcher._browser = object()
        return fetcher

    def test_fetch_rejects_file_scheme_before_navigation(self) -> None:
        import asyncio

        result = asyncio.run(self._fetcher().fetch("file:///etc/passwd"))
        self.assertFalse(result.success)
        self.assertIn("Unsafe URL", result.error or "")

    def test_fetch_rejects_metadata_ip_before_navigation(self) -> None:
        import asyncio

        result = asyncio.run(
            self._fetcher().fetch("http://169.254.169.254/latest/meta-data/")
        )
        self.assertFalse(result.success)
        self.assertIn("Unsafe URL", result.error or "")

    def test_screenshot_rejects_loopback_before_navigation(self) -> None:
        import asyncio

        result = asyncio.run(
            self._fetcher().screenshot("http://127.0.0.1:9222/", "/tmp/x.png")
        )
        self.assertIsNone(result.final_url)
        self.assertIn("Unsafe URL", result.error or "")


class TestSchemes(unittest.TestCase):
    def test_non_http_schemes_rejected(self) -> None:
        for bad in (
            "file:///etc/passwd",
            "ftp://example.com",
            "gopher://example.com",
            "data:text/plain,test",
            "javascript:alert(1)",
            "chrome://settings",
            "",
            "not a url",
            "http://",
        ):
            with self.subTest(url=bad):
                with self.assertRaises(UnsafeUrlError):
                    validate_public_http_url(bad)

    def test_http_and_https_accepted(self) -> None:
        for good in (
            "http://example.com",
            "https://example.com",
            "HTTPS://EXAMPLE.COM/path?q=1#frag",
        ):
            with self.subTest(url=good):
                self.assertIsNotNone(
                    validate_public_http_url(good, resolver=_PUBLIC_RESOLVER)
                )


class TestPrivateIPv4Literals(unittest.TestCase):
    def test_non_global_ranges_rejected(self) -> None:
        for bad in (
            "http://127.0.0.1",
            "http://127.8.8.8/",
            "http://10.0.0.1",
            "http://172.16.0.1",
            "http://172.31.255.255",
            "http://192.168.1.1",
            "http://169.254.169.254/latest/meta-data/",
            "http://0.0.0.0",
            "http://192.0.2.1",  # documentation range
            "http://224.0.0.1",  # multicast
            "http://255.255.255.255",  # broadcast
            "http://100.64.0.1",  # CGNAT shared range
        ):
            with self.subTest(url=bad):
                with self.assertRaises(UnsafeUrlError):
                    validate_public_http_url(bad)

    def test_adjacent_but_public_ranges_accepted(self) -> None:
        # Outside every blocked block: 172.32.x, 11.x, 170.x, 193.x are global.
        for good in (
            "http://172.32.0.1",
            "http://11.0.0.1",
            "http://170.0.0.1",
            "http://193.0.0.1",
        ):
            with self.subTest(url=good):
                self.assertTrue(is_safe_public_http_url(good))


class TestPrivateIPv6Literals(unittest.TestCase):
    def test_non_global_ipv6_rejected(self) -> None:
        for bad in (
            "http://[::1]/",
            "http://[fe80::1]/",
            "http://[fc00::1]/",
            "http://[fd00::1]/",
            "http://[::ffff:127.0.0.1]/",  # IPv4-mapped loopback
            "http://[2001:db8::1]/",  # documentation range
        ):
            with self.subTest(url=bad):
                with self.assertRaises(UnsafeUrlError):
                    validate_public_http_url(bad)


class TestLocalhostNames(unittest.TestCase):
    def test_localhost_names_rejected(self) -> None:
        for bad in (
            "http://localhost",
            "http://localhost:8080/admin",
            "http://sub.localhost/",
        ):
            with self.subTest(url=bad):
                with self.assertRaises(UnsafeUrlError):
                    validate_public_http_url(bad)


class TestCredentials(unittest.TestCase):
    def test_embedded_credentials_rejected(self) -> None:
        for bad in (
            "https://user:password@example.com",
            "https://user@example.com",
            "http://admin:secret@127.0.0.1/x",
        ):
            with self.subTest(url=bad):
                with self.assertRaises(UnsafeUrlError):
                    validate_public_http_url(bad)

    def test_query_params_are_not_credentials(self) -> None:
        self.assertTrue(
            is_safe_public_http_url(
                "https://example.com/?user=x&password=y",
                resolver=_PUBLIC_RESOLVER,
            )
        )


if __name__ == "__main__":
    unittest.main()
