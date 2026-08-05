from __future__ import annotations

from typing import Optional
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from src.contact.helpers import normalize_absolute_url

# platform keyword -> (host suffixes, canonical field name)
_PLATFORMS: dict[str, tuple[tuple[str, ...], str]] = {
    "facebook_url": (("facebook.com", "fb.com"), "facebook_url"),
    "instagram_url": (("instagram.com",), "instagram_url"),
    "linkedin_url": (("linkedin.com",), "linkedin_url"),
    "twitter_url": (("twitter.com", "x.com"), "twitter_url"),
    "youtube_url": (("youtube.com", "youtu.be"), "youtube_url"),
    "whatsapp_url": (("wa.me", "whatsapp.com", "api.whatsapp.com"), "whatsapp_url"),
}

# Paths that point at platform chrome rather than a business profile.
_SKIP_PATHS: dict[str, tuple[str, ...]] = {
    "facebook_url": (
        "/sharer", "/share", "/login", "/signup", "/privacy", "/help", "/policies",
        "/about", "/ads", "/pages/category", "/watch", "/events", "/groups", "/marketplace",
    ),
    "instagram_url": (
        "/accounts/", "/login", "/explore", "/reels", "/p/", "/stories/", "/about",
    ),
    "linkedin_url": (
        "/feed", "/jobs", "/login", "/signup", "/uas/", "/m/login", "/learning",
    ),
    "twitter_url": (
        "/intent", "/share", "/search", "/login", "/home", "/explore", "/notifications",
        "/messages", "/i/", "/hashtag",
    ),
    "youtube_url": (
        "/watch", "/results", "/playlist", "/about", "/trending",
    ),
    "whatsapp_url": ("/about", "/download", "/business", "/features", "/safety"),
}


def _host_without_www(url: str) -> str:
    host = (urlparse(url).netloc or "").lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def classify_social_url(raw: Optional[str]) -> Optional[str]:
    """Map a URL to a platform field name, or None when it is not a social profile."""
    text = (raw or "").strip()
    if not text:
        return None
    host = _host_without_www(text)
    path = urlparse(text).path or ""
    for keyword, (suffixes, _field) in _PLATFORMS.items():
        if not any(host == suffix or host.endswith("." + suffix) for suffix in suffixes):
            continue
        for skip in _SKIP_PATHS.get(keyword, ()):
            if skip in path:
                return None
        if keyword == "youtube_url" and not _is_youtube_profile(path, host):
            return None
        if keyword == "twitter_url" and host == "x.com" and not path.strip("/"):
            return None
        return keyword
    return None


def _is_youtube_profile(path: str, host: str) -> bool:
    if host == "youtu.be":
        return False
    return bool(
        path.startswith("/@")
        or path.startswith("/channel/")
        or path.startswith("/user/")
        or path.startswith("/c/")
    )


def extract_social_urls(html: str, base_url: Optional[str]) -> tuple[dict[str, str], list[str]]:
    """Find social profile links in HTML.

    Returns (platform -> normalized URL, ordered list of all found URLs).
    First profile found wins per platform; non-profile pages (sharer, login,
    platform chrome) are ignored.
    """
    found: dict[str, str] = {}
    ordered: list[str] = []
    if not html:
        return found, ordered

    soup = BeautifulSoup(html or "", "html.parser")
    for tag in soup.find_all("a", href=True):
        href = (tag.get("href") or "").strip()
        keyword = classify_social_url(href)
        if keyword is None:
            continue
        normalized = normalize_absolute_url(href, base_url)
        if not normalized:
            continue
        if normalized not in ordered:
            ordered.append(normalized)
        if keyword not in found:
            found[keyword] = normalized
    return found, ordered
