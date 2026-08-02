from __future__ import annotations

from typing import Any, Optional


def safe_str(value: Any) -> str:
    """Normalize any value to a stripped string, tolerating None."""
    if value is None:
        return ""
    return str(value).strip()


def safe_lower(value: Any) -> str:
    return safe_str(value).lower()


def has_text(value: Any) -> bool:
    return bool(safe_str(value))


def as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def clamp(value: float, low: int = 0, high: int = 100) -> int:
    return max(low, min(high, round(value)))


def detection_categories(detections: Optional[list[dict[str, Any]]]) -> set[str]:
    if not detections:
        return set()
    return {safe_str(item.get("category")).lower() for item in detections if isinstance(item, dict)}


def detection_names(detections: Optional[list[dict[str, Any]]]) -> set[str]:
    if not detections:
        return set()
    return {safe_str(item.get("technology_name")).lower() for item in detections if isinstance(item, dict)}


MODERN_FRAMEWORKS = {
    "react",
    "custom_react",
    "next.js",
    "nextjs",
    "vue",
    "vue.js",
    "nuxt",
    "gatsby",
    "svelte",
    "angular",
    "remix",
    "astro",
}

LEGACY_CMS = {"wordpress", "wix", "weebly", "squarespace", "blogger", "tumblr", "joomla", "drupal"}


def is_modern_platform(platform: str, names: set[str]) -> bool:
    return platform in MODERN_FRAMEWORKS or bool(names & MODERN_FRAMEWORKS)


def is_legacy_platform(platform: str) -> bool:
    return platform in LEGACY_CMS


def page_labels(crawl: Optional[dict[str, Any]]) -> set[str]:
    """Normalized page labels collected during the crawl (HOME, ABOUT, ...)."""
    if not crawl:
        return set()
    labels = set()
    for page in crawl.get("pages") or []:
        if isinstance(page, dict):
            label = safe_lower(page.get("label"))
            if label:
                labels.add(label)
    return labels


def page_types(crawl: Optional[dict[str, Any]]) -> set[str]:
    if not crawl:
        return set()
    types = set()
    for page in crawl.get("pages") or []:
        if isinstance(page, dict):
            page_type = safe_lower(page.get("page_type"))
            if page_type:
                types.add(page_type)
    return types


def has_contact_page(crawl: Optional[dict[str, Any]]) -> bool:
    labels = page_labels(crawl)
    types = page_types(crawl)
    return bool(labels & {"contact", "contacts", "contactus"}) or "contact" in types


def has_services_page(crawl: Optional[dict[str, Any]]) -> bool:
    labels = page_labels(crawl)
    types = page_types(crawl)
    return bool(labels & {"services", "service", "products", "product"}) or "services" in types


def has_about_page(crawl: Optional[dict[str, Any]]) -> bool:
    labels = page_labels(crawl)
    types = page_types(crawl)
    return bool(labels & {"about", "aboutus", "team"}) or "about" in types


def has_social_links(crawl: Optional[dict[str, Any]]) -> bool:
    if not crawl:
        return False
    urls = [safe_lower(url) for url in (crawl.get("social_urls") or []) if isinstance(url, str)]
    if not urls:
        links = crawl.get("links") or []
        urls = [safe_lower(link) for link in links if isinstance(link, str)]
    return any(
        domain in url
        for url in urls
        for domain in ("facebook.com", "instagram.com", "linkedin.com", "twitter.com", "x.com", "youtube.com")
    )


def contact_clues(crawl: Optional[dict[str, Any]]) -> list[str]:
    if not crawl:
        return []
    clues = crawl.get("contact_clues") or []
    return [safe_str(clue) for clue in clues if safe_str(clue)]


def is_https_url(url: Optional[str]) -> bool:
    return safe_lower(url).startswith("https://")
