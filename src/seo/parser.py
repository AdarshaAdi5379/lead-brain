from __future__ import annotations

import re
from typing import Optional
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup, Tag

from src.seo.base import PageEvidence

_PAGE_TYPE_TOKENS = {
    "about": "about",
    "about-us": "about",
    "contact": "contact",
    "contact-us": "contact",
    "service": "services",
    "services": "services",
    "home": "home",
}

_SKIPPED_SCHEMES = {"mailto", "tel", "javascript", "data", "ftp", "file"}


def _host_key(hostname: str) -> str:
    host = (hostname or "").strip().lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def _clean(value: Optional[str]) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", " ", value).strip()


def _infer_page_type(url: str, is_homepage: bool) -> Optional[str]:
    if is_homepage:
        return "home"
    path = (urlparse(url).path or "").lower().strip("/")
    tokens = [token for token in path.split("/") if token]
    for token in tokens:
        matched = _PAGE_TYPE_TOKENS.get(token)
        if matched:
            return matched
    return "other"


def extract_evidence(html: str, url: str, *, is_homepage: bool = False) -> PageEvidence:
    """Deterministically extract every SEO signal from a page's HTML.

    Uses BeautifulSoup's ``html.parser`` (never executes scripts), runs purely
    on the already-bounded HTML string, and performs no network access.
    """
    html = html or ""
    soup = BeautifulSoup(html, "html.parser")

    title_tag = soup.title
    title = _clean(title_tag.get_text(" ") if title_tag is not None else "")

    description_tag = soup.find("meta", attrs={"name": re.compile("^description$", re.IGNORECASE)})
    meta_description = _clean(description_tag.get("content")) if isinstance(description_tag, Tag) else ""

    canonical_tag = soup.find("link", attrs={"rel": re.compile(r"\bcanonical\b", re.IGNORECASE)})
    canonical_raw = _clean(canonical_tag.get("href")) if isinstance(canonical_tag, Tag) else ""
    canonical_url = urljoin(url, canonical_raw) if canonical_raw else None

    robots_tag = soup.find("meta", attrs={"name": re.compile("^robots$", re.IGNORECASE)})
    robots_meta = _clean(robots_tag.get("content")) if isinstance(robots_tag, Tag) else ""

    viewport_tag = soup.find("meta", attrs={"name": re.compile("^viewport$", re.IGNORECASE)})
    viewport_present = isinstance(viewport_tag, Tag)

    h1_count = len(soup.find_all("h1"))
    h2_count = len(soup.find_all("h2"))
    h3_count = len(soup.find_all("h3"))

    json_ld_tag = soup.find("script", attrs={"type": re.compile(r"application/ld\+json", re.IGNORECASE)})

    schema_present = False
    for tag in soup.find_all(True):
        itemtype = tag.get("itemtype")
        if itemtype and "schema.org" in str(itemtype).lower():
            schema_present = True
            break
        if tag.has_attr("itemscope"):
            schema_present = True
            break

    og_title_tag = soup.find("meta", attrs={"property": re.compile(r"^og:title$", re.IGNORECASE)})
    og_description_tag = soup.find("meta", attrs={"property": re.compile(r"^og:description$", re.IGNORECASE)})
    twitter_card_tag = soup.find("meta", attrs={"name": re.compile(r"^twitter:card$", re.IGNORECASE)})

    favicon_tag = soup.find("link", attrs={"rel": re.compile(r"\bicon\b", re.IGNORECASE)})

    internal_link_count, mixed_content_count = _link_counts(soup, url)
    images = [img for img in soup.find_all("img") if isinstance(img, Tag)]
    image_count = len(images)
    missing_alt = 0
    broken = 0
    for img in images:
        alt = (img.get("alt") or "").strip()
        if not alt:
            missing_alt += 1
        src = (img.get("src") or "").strip()
        if not src or src == "#" or src.lower().startswith("javascript:"):
            broken += 1

    word_count = _word_count(soup)

    lowered = html.lower()
    sitemap_reference = "sitemap.xml" in lowered or any(
        (link.get("rel") or "") and "sitemap" in " ".join(link.get("rel") or []).lower()
        for link in soup.find_all("link")
        if isinstance(link, Tag)
    )
    robots_txt_reference = "robots.txt" in lowered

    is_https = (urlparse(url).scheme or "").lower() == "https"

    return PageEvidence(
        url=url,
        is_https=is_https,
        title=title,
        meta_description=meta_description,
        canonical_url=canonical_url,
        robots_meta=robots_meta,
        viewport_present=viewport_present,
        h1_count=h1_count,
        h2_count=h2_count,
        h3_count=h3_count,
        word_count=word_count,
        image_count=image_count,
        images_missing_alt_count=missing_alt,
        images_broken_count=broken,
        json_ld_present=isinstance(json_ld_tag, Tag),
        schema_present=schema_present,
        og_title_present=isinstance(og_title_tag, Tag),
        og_description_present=isinstance(og_description_tag, Tag),
        twitter_card_present=isinstance(twitter_card_tag, Tag),
        favicon_present=isinstance(favicon_tag, Tag),
        internal_link_count=internal_link_count,
        mixed_content_count=mixed_content_count,
        sitemap_reference=sitemap_reference,
        robots_txt_reference=robots_txt_reference,
        page_type=_infer_page_type(url, is_homepage=is_homepage),
    )


def _word_count(soup: BeautifulSoup) -> int:
    for tag in soup.find_all(["script", "style", "noscript", "template"]):
        tag.decompose()
    text = soup.get_text(" ")
    return len(text.split())


def _link_counts(soup: BeautifulSoup, base_url: str) -> tuple[int, int]:
    base_host = _host_key(urlparse(base_url).hostname or "")
    internal = 0
    mixed_content = 0
    page_is_https = (urlparse(base_url).scheme or "").lower() == "https"

    for tag in soup.find_all("a", href=True):
        if not isinstance(tag, Tag):
            continue
        href = (tag.get("href") or "").strip()
        if not href:
            continue
        absolute = urljoin(base_url, href)
        parsed = urlparse(absolute)
        if parsed.scheme not in {"http", "https"}:
            continue
        if _host_key(parsed.hostname or "") == base_host:
            internal += 1
        if page_is_https and (parsed.scheme or "").lower() == "http":
            mixed_content += 1

    for tag in soup.find_all(["img", "script", "link", "iframe"], src=True):
        if not isinstance(tag, Tag):
            continue
        src = (tag.get("src") or "").strip()
        if page_is_https and src.lower().startswith("http://"):
            mixed_content += 1

    return internal, mixed_content
