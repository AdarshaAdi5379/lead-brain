from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any, Optional

from src.scraping.browser_fetch import FetchResult
from src.scraping.content_extractor import extract_contact_clues, parse_page
from src.scraping.content_merger import Section, merge_sections, trim_text
from src.scraping.link_extractor import Link, extract_internal_links, normalize_page_url
from src.scraping.page_cache import PageCache, content_hash
from src.scraping.page_ranker import find_contact_links, label_for_link, select_pages
from src.settings import (
    CRAWL_CACHE_DIR,
    CRAWL_CACHE_FILE,
    MAX_CRAWL_DEPTH,
    MAX_CRAWL_PAGES,
    MAX_PAGE_CHARACTERS,
    SEO_PAGE_HTML_MAX_CHARS,
)
from src.contact import ContactSignals, extract_contact_signals, merge_contact_signals

logger = logging.getLogger("lead.crawl")


@dataclass(frozen=True)
class CrawlMetadata:
    visited_pages: int  # pages fetched over the network (homepage included)
    selected_pages: int  # extra pages chosen by the ranker
    skipped_pages: int  # links filtered as boilerplate / low priority
    page_count: int  # pages included in the merged document
    failed_pages: int  # selected pages that could not be fetched
    total_characters: int  # characters in the merged document
    crawl_duration: float  # seconds
    cached_pages: int  # pages reused from the page cache without a fetch
    content_hash: str  # sha256 of the merged document


@dataclass(frozen=True)
class PageRecord:
    url: str
    label: str
    title: str
    text: str
    # Bounded raw HTML fragment kept for the deterministic local SEO audit.
    # Empty for legacy cache entries that never stored HTML.
    html: str = ""
    # Structured contact facts extracted from the raw HTML (empty set when
    # the page carried none or the HTML is unavailable).
    contact: ContactSignals = ContactSignals()


@dataclass(frozen=True)
class CrawlResult:
    url: str
    ok: bool
    error: Optional[str]
    merged_text: str
    contact_clues: tuple[str, ...]
    pages: tuple[PageRecord, ...]
    content_hash: str
    metadata: Optional[CrawlMetadata]
    contact_signals: ContactSignals = ContactSignals()

    def __bool__(self) -> bool:
        return self.ok


def _empty_crawl(url: str, error: str) -> CrawlResult:
    return CrawlResult(
        url=url,
        ok=False,
        error=error,
        merged_text="",
        contact_clues=(),
        pages=(),
        content_hash="",
        metadata=None,
        contact_signals=ContactSignals(),
    )


class FocusedCrawler:
    """Audits only the most relevant pages of a single business website.

    Exact homepage + at most ``max_pages - 1`` ranked internal pages, never
    recursing. Deterministic rules choose the pages, no AI involved.
    """

    def __init__(
        self,
        *,
        max_pages: int = MAX_CRAWL_PAGES,
        max_depth: int = MAX_CRAWL_DEPTH,
        max_page_characters: int = MAX_PAGE_CHARACTERS,
        cache: Optional[PageCache] = None,
    ) -> None:
        self._max_pages = max(1, int(max_pages))
        self._max_depth = max(1, int(max_depth))
        self._max_page_characters = max(1, int(max_page_characters))
        self._cache = cache or PageCache(CRAWL_CACHE_DIR, CRAWL_CACHE_FILE)

    async def crawl(
        self,
        fetcher: Any,
        home_url: str,
        *,
        home_fetch: Optional[FetchResult] = None,
    ) -> CrawlResult:
        started = time.monotonic()
        home_url = (home_url or "").strip()

        home_fetch = home_fetch or await fetcher.fetch(home_url)
        if not home_fetch.success:
            logger.warning("Homepage failed to load: %s — %s", home_url, home_fetch.error)
            return _empty_crawl(home_url, home_fetch.error or "Homepage failed")

        final_home_url = home_fetch.final_url or home_url
        logger.info("Homepage loaded: %s", final_home_url)
        home_html = home_fetch.html or ""

        links = extract_internal_links(home_html, final_home_url)
        logger.info("Found %d internal links", len(links))

        ranked_pages = self._max_pages - 1
        selection = select_pages(links, max_pages=ranked_pages)
        selected = list(self._exclude_homepage(selection.selected, final_home_url))

        # A contact page always gets crawled and visited first (when one exists
        # and fits the budget): contact facts reach our deterministic extractor
        # even when a small max_pages would otherwise drop it from the ranked
        # selection. Reserving a slot drops only the weakest ranked page.
        contact_links = self._exclude_homepage(find_contact_links(links), final_home_url)
        contact_link = contact_links[0] if contact_links else None
        contact_url: Optional[str] = None
        if contact_link is not None and self._max_pages > 1:
            if contact_link.url not in {link.url for link in selected}:
                if len(selected) >= ranked_pages:
                    selected.pop()
                selected.append(contact_link)
            selected = [link for link in selected if link.url != contact_link.url]
            selected.insert(0, contact_link)
            contact_url = contact_link.url
        logger.info("Ranked links")
        logger.info("Selected: %s", ", ".join(label_for_link(l) for l in selected) or "(none)")

        # Contact intelligence runs on the raw HTML *before* boilerplate
        # removal: headers/footers, forms and social icons are where contact
        # facts live, and the visible-text extractor deliberately strips them.
        home_contact = extract_contact_signals(home_html, final_home_url, page_label="HOME")

        home_content = parse_page(home_html, final_home_url)

        sections: list[Section] = []
        records: list[PageRecord] = []
        clues = list(extract_contact_clues(home_html, final_home_url))

        visited = 0
        cached_pages = 0
        failed: list[str] = []

        if home_content.text.strip():
            home_text = trim_text(home_content.text, max_chars=self._max_page_characters)
            sections.append(Section(label="HOME", url=final_home_url, text=home_text))
            records.append(
                PageRecord(
                    url=final_home_url,
                    label="HOME",
                    title=home_content.title,
                    text=home_text,
                    html=self._bounded_html(home_html),
                    contact=home_contact,
                )
            )

        for link in selected:
            label = label_for_link(link)
            cached_text = self._cache.get(link.url)
            if cached_text is not None:
                cached_pages += 1
                page_text = cached_text
                page_title = ""
                page_url = link.url
                page_html = self._cache.get_html(link.url)
                page_contact = (
                    extract_contact_signals(page_html, page_url, page_label=label)
                    if page_html
                    else ContactSignals()
                )
                # Rebuild contact clues from cached plain text (emails only).
                clues.extend(extract_contact_clues(cached_text, link.url))
            else:
                page_fetch = await fetcher.fetch(link.url)
                if not page_fetch.success:
                    failed.append(link.url)
                    logger.warning("Page failed to load: %s — %s", link.url, page_fetch.error)
                    continue
                visited += 1
                page_url = page_fetch.final_url or link.url
                page_contact = extract_contact_signals(
                    page_fetch.html or "", page_url, page_label=label
                )
                page_content = parse_page(page_fetch.html or "", page_url)
                page_text = page_content.text
                page_title = page_content.title
                page_html = self._bounded_html(page_fetch.html or "")
                clues.extend(extract_contact_clues(page_fetch.html or "", page_url))
                self._cache.put(link.url, page_text, html=page_html)

            if not page_text.strip():
                logger.info("Skipping empty page: %s", link.url)
                continue

            trimmed = trim_text(page_text, max_chars=self._max_page_characters)
            sections.append(Section(label=label, url=page_url, text=trimmed))
            records.append(
                PageRecord(
                    url=page_url,
                    label=label,
                    title=page_title,
                    text=trimmed,
                    html=page_html,
                    contact=page_contact,
                )
            )

        unique_clues = self._dedupe_clues(clues)
        if unique_clues:
            sections.append(Section(label="CONTACT", url="", text="\n".join(unique_clues)))

        merged_text = merge_sections(sections)
        visited += 1  # homepage
        logger.info("Visited %d pages", visited)
        logger.info("Merged %s characters", len(merged_text))

        email_values = sorted(
            {candidate.value.lower() for record in records for candidate in record.contact.email_candidates}
        )
        phone_values = sorted(
            {candidate.value for record in records for candidate in record.contact.phone_candidates}
        )
        used_sources = sorted(
            {
                candidate.source
                for record in records
                for candidate in (*record.contact.email_candidates, *record.contact.phone_candidates)
            }
        )
        contact_line = f"; contact page: {contact_url}" if contact_url else ""
        logger.info(
            "Crawl result: %d pages, %d emails, %d phones, sources=%s%s",
            visited,
            len(email_values),
            len(phone_values),
            ",".join(used_sources) or "none",
            contact_line,
        )

        metadata = CrawlMetadata(
            visited_pages=visited,
            selected_pages=len(selected),
            skipped_pages=len(selection.skipped),
            page_count=len(records),
            failed_pages=len(failed),
            total_characters=len(merged_text),
            crawl_duration=time.monotonic() - started,
            cached_pages=cached_pages,
            content_hash=content_hash(merged_text),
        )
        return CrawlResult(
            url=final_home_url,
            ok=True,
            error=None,
            merged_text=merged_text,
            contact_clues=tuple(unique_clues),
            pages=tuple(records),
            content_hash=metadata.content_hash,
            metadata=metadata,
            contact_signals=merge_contact_signals(record.contact for record in records),
        )

    # --- helpers ---------------------------------------------------------

    @staticmethod
    def _bounded_html(html: str) -> str:
        """Cap the raw HTML retained for the SEO audit (memory + disk bound)."""
        return (html or "")[:SEO_PAGE_HTML_MAX_CHARS]

    @staticmethod
    def _exclude_homepage(links: list[Link], home_url: str) -> list[Link]:
        home_key = normalize_page_url(home_url)
        return [link for link in links if normalize_page_url(link.url) != home_key]

    @staticmethod
    def _dedupe_clues(clues: list[str]) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for line in clues:
            key = line.lower()
            if key not in seen:
                seen.add(key)
                out.append(line)
        return out


# --- smoke / CLI runner -----------------------------------------------------


async def _crawl_one(url: str, max_pages: int) -> CrawlResult:
    from src.scraping.browser_fetch import PlaywrightFetcher

    crawler = FocusedCrawler(max_pages=max(1, int(max_pages)))
    async with PlaywrightFetcher() as fetcher:
        return await crawler.crawl(fetcher, url)


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Focused crawler smoke test (v2).")
    parser.add_argument("url", help="Homepage URL to crawl (e.g. https://example.com)")
    parser.add_argument(
        "--pages",
        type=int,
        default=MAX_CRAWL_PAGES,
        help=f"Max pages to visit including the homepage (default {MAX_CRAWL_PAGES})",
    )
    args = parser.parse_args()

    result = asyncio.run(_crawl_one(args.url, args.pages))
    if not result.ok:
        print(f"crawl failed: {result.error}")
        return
    print(f"--- merged ({len(result.merged_text)} chars) ---")
    print(result.merged_text[:2000], "…" if len(result.merged_text) > 2000 else "")
    print(f"--- metadata: {result.metadata!r}")


if __name__ == "__main__":
    main()