from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse, urlunparse

from bs4 import BeautifulSoup, Tag

# Non-HTML assets and downloads we never audit.
IGNORED_EXTENSIONS = {
    ".pdf",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".svg",
    ".ico",
    ".zip",
    ".tar",
    ".gz",
    ".css",
    ".js",
    ".xml",
    ".json",
    ".rss",
    ".atom",
    ".txt",
    ".doc",
    ".docx",
    ".xls",
    ".xlsx",
    ".ppt",
    ".pptx",
    ".mp3",
    ".mp4",
    ".mov",
    ".avi",
    ".webm",
    ".wav",
}

SKIPPED_SCHEMES = {"mailto", "tel", "javascript", "data", "ftp", "file"}


@dataclass(frozen=True)
class Link:
    url: str  # absolute, normalized (no fragment)
    text: str  # trimmed anchor text (may be empty)


def _host_key(hostname: str) -> str:
    host = (hostname or "").strip().lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def _clean_anchor(tag: Tag) -> str:
    text = re.sub(r"\s+", " ", tag.get_text(" ") or "").strip()
    return text


def normalize_page_url(raw_url: str) -> str:
    """Normalize an absolute URL into a stable identity for dedupe/rank.

    Lowercases the host + path, drops the fragment/query, and collapses a bare
    trailing slash so '/about' and '/about/' match."""
    parsed = urlparse(raw_url.strip())
    netloc = (parsed.netloc or "").lower()
    path = (parsed.path or "/").lower()
    if path != "/":
        path = path.rstrip("/")
    return urlunparse((parsed.scheme, netloc, path, "", "", ""))


def extract_internal_links(html: str, base_url: str) -> list[Link]:
    """Return same-domain HTTP(S) links from a rendered page's HTML.

    - Resolves relative URLs against ``base_url``.
    - Drops external domains, mailto/tel/javascript/data links, asset
      extensions, and pure-fragment links.
    - Normalizes and de-duplicates, preserving first-seen order.
    """
    soup = BeautifulSoup(html or "", "html.parser")
    base_netloc = _host_key(urlparse(base_url).hostname or "")

    links: list[Link] = []
    seen: set[str] = set()

    for tag in soup.find_all("a", href=True):
        if not isinstance(tag, Tag):
            continue
        href = (tag.get("href") or "").strip()
        if not href:
            continue

        scheme = urlparse(href).scheme.lower()
        if scheme in SKIPPED_SCHEMES:
            continue

        absolute = urljoin(base_url, href)
        parsed = urlparse(absolute)
        if parsed.scheme not in {"http", "https"}:
            continue
        if _host_key(parsed.hostname or "") != base_netloc:
            continue

        path_lower = (parsed.path or "").lower()
        if any(path_lower.endswith(ext) for ext in IGNORED_EXTENSIONS):
            continue

        # A pure fragment or pure query link points back at the same page.
        if not (parsed.path or "").strip("/") and (parsed.fragment or parsed.query):
            continue

        normalized = normalize_page_url(absolute)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)

        links.append(Link(url=normalized, text=_clean_anchor(tag)))

    return links