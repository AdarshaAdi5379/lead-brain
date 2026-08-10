from __future__ import annotations

import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Callable, Optional

from bs4 import BeautifulSoup

from src.enrichment.base import LeadContext
from src.enrichment.config import EnrichmentConfig
from src.enrichment.normalizer import clean_candidate_url

# Result link selectors for the anonymous HTML endpoint. The second is a
# fallback in case DuckDuckGo changes markup over time.
_RESULT_SELECTORS = ("a.result__a", "a.result-link")

_REDIRECT_MARKERS = ("//duckduckgo.com/l/", "/l/?uddg=")


def build_search_query(lead: LeadContext) -> str:
    """Compose the discovery query: business name + location + category."""
    parts = [lead.business_name, lead.city, lead.state, lead.category]
    return " ".join(str(part) for part in parts if part and str(part).strip())


def _decode_result_href(href: str) -> str:
    """Unwrap DuckDuckGo's /l/?uddg= redirect wrapper back to the real URL."""
    if any(marker in href for marker in _REDIRECT_MARKERS):
        query = urllib.parse.urlparse(href).query
        wrapped = urllib.parse.parse_qs(query).get("uddg")
        if wrapped:
            return wrapped[0]
    return href


def _parse_results(html: str) -> list[str]:
    """Extract clean, deduplicated organic result URLs from the search page."""
    soup = BeautifulSoup(html, "html.parser")
    urls: list[str] = []
    seen: set[str] = set()
    for selector in _RESULT_SELECTORS:
        for anchor in soup.select(selector):
            href = anchor.get("href") or ""
            decoded = _decode_result_href(href)
            url = clean_candidate_url(decoded)
            if not url or url in seen:
                continue
            seen.add(url)
            urls.append(url)
        if urls:
            break
    return urls


def search_web(query: str, config: EnrichmentConfig) -> list[str]:
    """Anonymous web search for candidate URLs (free, no account required).

    Issues one polite GET against the DuckDuckGo HTML endpoint with a single
    retry on transient failures, then returns up to ``max_search_results``
    normalized organic results. Search output is discovery only: every URL
    must still pass deterministic verification before it can be stored.
    """
    params = urllib.parse.urlencode({"q": query})
    url = f"{config.search_url}?{params}"
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": config.user_agent,
            "Accept": "text/html,application/xhtml+xml",
        },
    )

    last_error: Optional[BaseException] = None
    for attempt in range(2):
        try:
            with urllib.request.urlopen(request, timeout=config.search_timeout_s) as response:
                html = response.read(1_000_000).decode("utf-8", errors="replace")
            return _parse_results(html)[: config.max_search_results]
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError) as exc:
            last_error = exc
            if attempt == 0:
                time.sleep(0.5)
    if isinstance(last_error, urllib.error.HTTPError):
        raise RuntimeError(
            f"Web search failed: HTTP {last_error.code} from {config.search_url}"
        ) from last_error
    raise RuntimeError(f"Web search failed: {last_error}") from last_error


SearchClient = Callable[[str], list[str]]