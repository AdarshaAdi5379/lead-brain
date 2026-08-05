from __future__ import annotations

from typing import Any, Optional

from src.contact.forms import detect_contact_form
from src.contact.helpers import (
    clean_text,
    is_contact_page,
    normalize_absolute_url,
    normalize_email,
    normalize_phone,
    page_priority_key,
)
from src.contact.jsonld import extract_jsonld
from src.contact.schema import ContactSignals, merge_contact_signals
from src.contact.social import classify_social_url, extract_social_urls


def extract_contact_signals(
    html: str,
    page_url: Optional[str],
    *,
    page_label: Optional[str] = None,
) -> ContactSignals:
    """Extract all contact facts from a single page's raw HTML.

    Runs before boilerplate removal so headers/footers, social icons and
    forms (which the visible-text extractor deliberately strips) are still
    present. Pure and deterministic; never raises.
    """
    if not html:
        return ContactSignals()

    page_url = clean_text(page_url) or None
    structured = extract_jsonld(html)
    social_map, social_order = extract_social_urls(html, page_url)
    form_url = detect_contact_form(html, page_url, page_label=page_label)

    for raw_url in structured.get("same_as") or []:
        keyword = classify_social_url(raw_url)
        normalized = normalize_absolute_url(raw_url, page_url)
        if keyword and not social_map.get(keyword):
            social_map[keyword] = normalized or normalize_absolute_url(raw_url, None) or raw_url
        if normalized and normalized not in social_order:
            social_order.append(normalized)

    service_areas = structured.get("service_areas") or []
    social_urls = [url for url in social_order if url]

    return ContactSignals(
        owner_name=clean_text(structured.get("owner_name")),
        address=clean_text(structured.get("address")),
        postal_code=clean_text(structured.get("postal_code")),
        country=clean_text(structured.get("country")),
        opening_hours=clean_text(structured.get("opening_hours")),
        phone=normalize_phone(structured.get("telephone")),
        email=normalize_email(structured.get("email")),
        facebook_url=social_map.get("facebook_url"),
        instagram_url=social_map.get("instagram_url"),
        linkedin_url=social_map.get("linkedin_url"),
        twitter_url=social_map.get("twitter_url"),
        youtube_url=social_map.get("youtube_url"),
        whatsapp_url=social_map.get("whatsapp_url"),
        contact_page_url=page_url if is_contact_page(page_label, page_url) else None,
        contact_form_url=form_url,
        service_areas=list(service_areas),
        social_urls=social_urls,
    )


def _page_contact(page: Any) -> Optional[ContactSignals]:
    """Best-effort contact signals attached to a crawl page record."""
    try:
        return page.contact if isinstance(page.contact, ContactSignals) else None
    except AttributeError:
        return None


def extract_contact_signals_from_crawl(crawl: Any) -> ContactSignals:
    """Aggregate per-page signals across a CrawlResult.

    Pages are merged in priority order (homepage -> contact -> about -> rest)
    so the most reliable page's facts win. Returns an empty set when the crawl
    carried no pages or no per-page signals.
    """
    if crawl is None:
        return ContactSignals()
    if getattr(crawl, "contact_signals", None) is not None:
        return crawl.contact_signals
    pages = list(getattr(crawl, "pages", None) or [])
    pages.sort(key=lambda page: page_priority_key(getattr(page, "label", "")))
    return merge_contact_signals(_page_contact(page) for page in pages)


def extract_contact_signals_from_fetch(fetch: Any) -> ContactSignals:
    """Homepage-only contact extraction for the no-crawl pipeline path."""
    if fetch is None:
        return ContactSignals()
    html = getattr(fetch, "html", None) or ""
    page_url = getattr(fetch, "final_url", None) or getattr(fetch, "url", None) or None
    return extract_contact_signals(html, page_url, page_label="HOME")
