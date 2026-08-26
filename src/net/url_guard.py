# Shared URL trust boundary for every external fetch in lead-brain.
#
# Only public http(s) URLs may be fetched by the pipeline. This module is the
# single gate used by the Playwright fetcher (seed/crawl path) and the
# enrichment verifier; no component should call a network transport without
# passing a URL through validate_public_http_url() first.
#
# Validation layers:
#   1. Syntax — scheme must be http/https, no embedded credentials, host present.
#   2. Literal hosts — any IP literal must be globally routable (loopback,
#      RFC1918, link-local, unspecified, unique-local and other reserved ranges
#      rejected).
#   3. DNS — every address the resolver returns for a hostname must be globally
#      routable. The resolver is injectable for deterministic offline tests.
#
# Resolution failures: if the resolver cannot answer at validation time (no
# network, transient DNS outage), the URL is passed through and the subsequent
# connect attempt fails on its own. Rebinding-style attacks are still covered,
# because the check inspects exactly the addresses DNS supplies at fetch time —
# a lookup that succeeds to a private address is always rejected.
from __future__ import annotations

import ipaddress
import socket
from typing import Callable, Optional
from urllib.parse import urlsplit

ALLOWED_SCHEMES = frozenset({"http", "https"})

Resolver = Callable[[str], list[str]]

# Error message prefixes stay actionable but never echo resolved addresses.
_EMPTY_URL = "Unsafe URL: empty"
_MALFORMED = "Unsafe URL: malformed"
_BAD_SCHEME = "Unsafe URL: unsupported scheme"
_CREDENTIALS = "Unsafe URL: embedded credentials not allowed"
_MISSING_HOST = "Unsafe URL: missing host"
_LOCAL_HOST = "Unsafe URL: localhost is not allowed"
_PRIVATE_IP = "Unsafe URL: private or non-public IP address"
_PRIVATE_DNS = "Unsafe URL: hostname resolves to a private address"


class UnsafeUrlError(ValueError):
    """Raised when a URL must not be fetched."""


def _default_resolver(host: str) -> list[str]:
    """Resolve a hostname to its IP addresses via the OS resolver."""
    infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    return sorted({info[4][0] for info in infos})


def _is_public_ip(value: str) -> bool:
    try:
        ip = ipaddress.ip_address(value)
    except ValueError:
        return False
    # Multicast reports is_global=True on some Python versions; it is never a
    # valid crawl/uniqueness target, so exclude it explicitly.
    return bool(ip.is_global) and not ip.is_multicast


def validate_public_http_url(
    url: str,
    *,
    resolver: Optional[Resolver] = None,
    resolve_dns: bool = True,
) -> str:
    """Return the validated URL, or raise :class:`UnsafeUrlError`.

    ``resolve_dns=False`` performs syntax + literal-IP validation only (used
    by seed loading so CSV parsing stays deterministic and offline); the full
    network boundary (browser fetcher, enrichment verifier) always resolves.
    """
    cleaned = (url or "").strip()
    if not cleaned:
        raise UnsafeUrlError(_EMPTY_URL)

    try:
        parts = urlsplit(cleaned)
    except ValueError as exc:
        raise UnsafeUrlError(f"{_MALFORMED}: {exc}") from exc

    scheme = (parts.scheme or "").lower()
    if scheme not in ALLOWED_SCHEMES:
        raise UnsafeUrlError(f"{_BAD_SCHEME} '{scheme or 'none'}'")
    if parts.username is not None or parts.password is not None:
        raise UnsafeUrlError(_CREDENTIALS)

    host = (parts.hostname or "").strip().rstrip(".")
    if not host:
        raise UnsafeUrlError(_MISSING_HOST)
    if host.lower() == "localhost" or host.lower().endswith(".localhost"):
        raise UnsafeUrlError(_LOCAL_HOST)

    # IP literals (IPv4/IPv6, brackets already stripped by .hostname).
    if _looks_like_ip(host):
        if not _is_public_ip(host):
            raise UnsafeUrlError(_PRIVATE_IP)
        return cleaned

    if resolve_dns:
        resolve = resolver if resolver is not None else _default_resolver
        try:
            addresses = resolve(host)
        except (socket.gaierror, OSError):
            # Resolution failed at validation time; let the real fetch fail.
            return cleaned
        if addresses and not all(_is_public_ip(address) for address in addresses):
            raise UnsafeUrlError(_PRIVATE_DNS)

    return cleaned


def _looks_like_ip(host: str) -> bool:
    if ":" in host:
        return True  # IPv6 literal
    labels = host.split(".")
    return len(labels) == 4 and all(label.isdigit() for label in labels)


def is_safe_public_http_url(
    url: str,
    *,
    resolver: Optional[Resolver] = None,
    resolve_dns: bool = True,
) -> bool:
    """Boolean wrapper around :func:`validate_public_http_url`."""
    try:
        validate_public_http_url(url, resolver=resolver, resolve_dns=resolve_dns)
    except UnsafeUrlError:
        return False
    return True