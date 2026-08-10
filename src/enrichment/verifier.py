from __future__ import annotations

import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Optional

from bs4 import BeautifulSoup

from src.enrichment.base import LeadContext
from src.enrichment.match import score_candidate

_NOISE_TAGS = ("script", "style", "noscript", "svg", "template", "iframe")

# Cap for the visible-text passed to the matcher (bounds memory).
_MAX_VERIFIED_TEXT_CHARS = 120_000


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
    """
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": user_agent,
            "Accept": "text/html,application/xhtml+xml",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_s) as response:
            content_type = (response.headers.get("Content-Type") or "").lower()
            if "html" not in content_type and "xml" not in content_type:
                return PageVerification(
                    url, False, error=f"Non-HTML response ({content_type or 'unknown'})"
                )
            raw = response.read(max_bytes)
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError) as exc:
        return PageVerification(url, False, error=str(exc)[:300])

    decoded = raw.decode("utf-8", errors="replace")
    soup = BeautifulSoup(decoded, "html.parser")
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    return PageVerification(
        url,
        True,
        title=title[:500],
        text=_visible_text(soup)[:_MAX_VERIFIED_TEXT_CHARS],
    )


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
    failed (score 0, empty signals).
    """
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