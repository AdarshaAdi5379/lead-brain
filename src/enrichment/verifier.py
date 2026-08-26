from __future__ import annotations

import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Optional

from bs4 import BeautifulSoup

from src.enrichment.base import LeadContext
from src.enrichment.match import score_candidate
from src.net.url_guard import UnsafeUrlError, validate_public_http_url

_NOISE_TAGS = ("script", "style", "noscript", "svg", "template", "iframe")

# Cap for the visible-text passed to the matcher (bounds memory).
_MAX_VERIFIED_TEXT_CHARS = 120_000

# Redirect handling: urllib's automatic following is DISABLED so that every
# hop passes the URL trust boundary before the next request. The hop cap keeps
# urllib's historical default (10) and all timeout/byte limits are unchanged.
_REDIRECT_CODES = frozenset({301, 302, 303, 307, 308})
_MAX_REDIRECT_HOPS = 10


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Suppress urllib's auto-follow; redirects are validated manually."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D401
        return None


def _open_with_no_redirect(request: urllib.request.Request, timeout_s: float):
    """Single network seam used by fetch_page (tests patch this callable)."""
    opener = urllib.request.build_opener(_NoRedirectHandler())
    return opener.open(request, timeout=timeout_s)


@dataclass(frozen=True)
class PageVerification:
    """Bounded fetch result for one candidate URL."""

    url: str
    ok: bool
    title: str = ""
    text: str = ""
    error: Optional[str] = None


def _visible_text(soup: BeautifulSoup) -> str:
    for tag in soup(_NOISE_TAGS):
        tag.decompose()
    return soup.get_text(" ")


def _read_html_response(response, url: str, max_bytes: int) -> PageVerification:
    content_type = ""
    try:
        content_type = (response.headers.get("Content-Type") or "").lower()
    except Exception:  # pragma: no cover - defensive header access
        content_type = ""
    if "html" not in content_type and "xml" not in content_type:
        return PageVerification(
            url, False, error=f"Non-HTML response ({content_type or 'unknown'})"
        )
    raw = response.read(max_bytes)

    decoded = raw.decode("utf-8", errors="replace")
    soup = BeautifulSoup(decoded, "html.parser")
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    return PageVerification(
        url,
        True,
        title=title[:500],
        text=_visible_text(soup)[:_MAX_VERIFIED_TEXT_CHARS],
    )


def fetch_page(
    url: str,
    *,
    timeout_s: float = 10.0,
    max_bytes: int = 300_000,
    user_agent: str = "lead-brain/1.0 (local lead finder; enrichment)",
) -> PageVerification:
    """Fetch a candidate homepage with strict bounds (stdlib urllib only).

    Non-HTML responses, timeouts and HTTP errors all fail verification: a
    candidate that cannot be fetched is never accepted. Oversized pages are
    truncated to ``max_bytes`` (never rejected) — the title and brand signals
    live at the top of the document.

    SSRF boundary: the initial URL and every redirect destination must pass
    ``validate_public_http_url``; private/internal hosts are never requested.
    """
    current: str
    try:
        current = validate_public_http_url(url)
    except UnsafeUrlError as exc:
        return PageVerification(url, False, error=str(exc))

    hops = 0
    while True:
        request = urllib.request.Request(
            current,
            headers={
                "User-Agent": user_agent,
                "Accept": "text/html,application/xhtml+xml",
            },
        )
        try:
            response = _open_with_no_redirect(request, timeout_s)
        except urllib.error.HTTPError as exc:
            code = exc.code if exc.code is not None else 0
            location = ""
            if exc.headers is not None:
                location = (exc.headers.get("Location") or "").strip()
            try:
                exc.close()
            except Exception:  # pragma: no cover - defensive close
                pass
            if code in _REDIRECT_CODES and hops < _MAX_REDIRECT_HOPS:
                if not location:
                    return PageVerification(
                        url, False, error=f"Unsafe redirect blocked: missing Location ({code})"
                    )
                target = urllib.parse.urljoin(current, location)
                try:
                    current = validate_public_http_url(target)
                except UnsafeUrlError as blocked:
                    # Never request the unsafe destination.
                    return PageVerification(url, False, error=f"Unsafe redirect blocked: {blocked}")
                hops += 1
                continue
            return PageVerification(url, False, error=str(exc)[:300])
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            return PageVerification(url, False, error=str(exc)[:300])

        try:
            return _read_html_response(response, url, max_bytes)
        finally:
            try:
                response.close()
            except Exception:  # pragma: no cover - best-effort close
                pass


def verify_candidate(
    candidate_url: str,
    *,
    lead: LeadContext,
    timeout_s: float,
    max_bytes: int,
    user_agent: str,
    fetcher=None,
) -> tuple[Optional[PageVerification], float, dict[str, float]]:
    """Fetch and deterministically score one candidate.

    Returns ``(page, score, signals)`` where ``page`` is None when the fetch
    failed (score 0, empty signals). Unsafe candidates are rejected before
    any fetcher (network or injected) is consulted and therefore never reach
    matching — nor the enrichment cache as a positive result.
    """
    try:
        candidate_url = validate_public_http_url(candidate_url, resolve_dns=False)
    except UnsafeUrlError as exc:
        return PageVerification(candidate_url, False, error=str(exc)), 0.0, {}

    if fetcher is not None:
        page = fetcher(candidate_url)
    else:
        page = fetch_page(
            candidate_url,
            timeout_s=timeout_s,
            max_bytes=max_bytes,
            user_agent=user_agent,
        )
    if not page.ok:
        return page, 0.0, {}
    score, signals = score_candidate(candidate_url, title=page.title, text=page.text, lead=lead)
    return page, score, signals