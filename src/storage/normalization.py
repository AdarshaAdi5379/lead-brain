from __future__ import annotations

from typing import Optional
from urllib.parse import urlparse, urlunparse


def normalize_url_for_dedupe(raw_url: Optional[str]) -> str:
    """
    Normalize a website URL into a stable key for deduplication.

    v1 rules (intentionally conservative):
    - Trim whitespace
    - Ensure a scheme exists (assume https:// when missing)
    - Lowercase hostname
    - Strip leading 'www.'
    - Drop default ports (80/443)
    - Drop querystring + fragment (commonly tracking params)
    - Strip trailing slash (except root)
    """

    if not raw_url:
        return ""

    url = raw_url.strip()
    if not url:
        return ""

    if "://" not in url:
        url = f"https://{url}"

    parsed = urlparse(url)

    hostname = (parsed.hostname or "").strip().lower()
    if hostname.startswith("www."):
        hostname = hostname[4:]

    port = parsed.port
    netloc = hostname
    if port and not (
        (parsed.scheme == "http" and port == 80) or (parsed.scheme == "https" and port == 443)
    ):
        netloc = f"{hostname}:{port}"

    path = parsed.path or ""
    if path != "/":
        path = path.rstrip("/")

    normalized = urlunparse(
        (
            "https",
            netloc,
            path,
            "",  # params (unused)
            "",  # query
            "",  # fragment
        )
    )

    return normalized

