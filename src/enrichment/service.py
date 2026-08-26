from __future__ import annotations

import logging
import sqlite3
from dataclasses import replace
from datetime import datetime, timezone
from typing import Callable, Optional

from src.enrichment.base import (
    FOUND,
    LOW_CONFIDENCE,
    NOT_FOUND,
    FAILED,
    NOT_NEEDED,
    EnrichmentCandidate,
    EnrichmentResult,
    LeadContext,
    WEB_SEARCH,
)
from src.enrichment.cache import CacheEntry, EnrichmentCache, query_key
from src.enrichment.config import EnrichmentConfig
from src.enrichment.match import email_domain_candidate, score_candidate
from src.enrichment.report import EnrichmentReport
from src.enrichment.search import SearchClient, build_search_query, search_web
from src.enrichment.verifier import PageVerification, fetch_page
from src.net.url_guard import UnsafeUrlError, validate_public_http_url


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _collect_candidates(
    lead: LeadContext,
    config: EnrichmentConfig,
    search: SearchClient,
) -> list[EnrichmentCandidate]:
    """Candidate URLs from the free sources, deduplicated and bounded."""
    candidates: list[EnrichmentCandidate] = []
    seen: set[str] = set()

    email_url = email_domain_candidate(lead.email)
    if email_url:
        seen.add(email_url)
        candidates.append(EnrichmentCandidate(email_url, "email_domain"))

    if config.search_enabled:
        try:
            for url in search(build_search_query(lead)):
                if url not in seen:
                    seen.add(url)
                    candidates.append(EnrichmentCandidate(url, WEB_SEARCH))
        except Exception:
            # Search discovery is best-effort; the email-domain candidate (if
            # any) is still usable, otherwise the lead ends up not_found.
            pass
    return candidates[: config.max_candidates]


def _best_verified(
    candidates: list[EnrichmentCandidate],
    config: EnrichmentConfig,
    fetch: Callable[[str], PageVerification],
    lead: LeadContext,
) -> Optional[tuple[EnrichmentCandidate, float, dict[str, float]]]:
    """Fetch and score candidates; return the strongest verified one."""
    best: Optional[tuple[EnrichmentCandidate, float, dict[str, float]]] = None
    for candidate in candidates:
        # SSRF boundary: unsafe candidates are never fetched or scored, so
        # they can never be accepted or cached as a positive result — even
        # when the transport is injected/mocked.
        try:
            validate_public_http_url(candidate.url, resolve_dns=False)
        except UnsafeUrlError:
            continue
        page = fetch(candidate.url)
        if not page.ok:
            continue
        score, signals = score_candidate(
            candidate.url, title=page.title, text=page.text, lead=lead
        )
        if best is None or score > best[1]:
            best = (candidate, score, signals)
    return best


def _enrich_one(
    lead: LeadContext,
    config: EnrichmentConfig,
    search: SearchClient,
    fetch: Callable[[str], PageVerification],
) -> EnrichmentResult:
    try:
        candidates = _collect_candidates(lead, config, search)
        if not candidates:
            return EnrichmentResult(NOT_FOUND, checked_at=_now())

        best = _best_verified(candidates, config, fetch, lead)
        if best is None:
            return EnrichmentResult(
                FAILED,
                last_error="No candidate page could be fetched for verification",
                checked_at=_now(),
            )

        candidate, score, _signals = best
        rounded = round(score, 3)
        if score >= config.accept_threshold:
            return EnrichmentResult(
                FOUND,
                website_url=candidate.url,
                source=candidate.source,
                confidence=rounded,
                checked_at=_now(),
            )
        return EnrichmentResult(
            LOW_CONFIDENCE,
            last_error=f"Best candidate {candidate.url} scored {rounded}",
            confidence=rounded,
            checked_at=_now(),
        )
    except Exception as exc:  # enrichment must never break the pipeline
        return EnrichmentResult(FAILED, last_error=str(exc)[:300], checked_at=_now())


def _seed_with_result(seed, result: EnrichmentResult):
    return replace(
        seed,
        url=result.website_url,
        enrichment_status=result.status,
        enrichment_source=result.source,
        enrichment_confidence=result.confidence,
        enrichment_last_error=result.last_error,
        enrichment_last_checked_at=result.checked_at,
    )


def run_enrichment(
    connection: sqlite3.Connection,
    seeds: list[object],
    config: EnrichmentConfig,
    *,
    search_client: Optional[SearchClient] = None,
    fetcher: Optional[Callable[[str], PageVerification]] = None,
    logger: Optional[logging.Logger] = None,
) -> tuple[list[object], EnrichmentReport]:
    """Website enrichment pre-pass over the seed list.

    Every seed without a website URL is looked up through the free sources
    (OSM tags already surface via discovery; here: email-domain + web search),
    verified deterministically, and updated in place via ``dataclasses.replace``
    — a seed with a verified website flows into the normal crawl pipeline; a
    seed without one stays valid with its enrichment status recorded.
    """
    report = EnrichmentReport()
    log = logger or logging.getLogger("lead.enrichment")

    if not config.enabled:
        return seeds, report

    cache = EnrichmentCache(connection, ttl_days=config.cache_ttl_days)
    search = search_client or (lambda query, c=config: search_web(query, c))
    fetch = fetcher or (
        lambda url, c=config: fetch_page(
            url,
            timeout_s=c.fetch_timeout_s,
            max_bytes=c.max_fetch_bytes,
            user_agent=c.user_agent,
        )
    )

    enriched_seeds: list[object] = []
    for seed in seeds:
        if seed.url:
            report.record(NOT_NEEDED)
            enriched_seeds.append(seed)
            continue

        lead = LeadContext.from_seed(seed)
        if not lead.business_name:
            report.record(NOT_NEEDED)
            enriched_seeds.append(seed)
            continue

        key = query_key(lead)
        cached = cache.get(key)
        if cached is not None:
            result = EnrichmentResult(
                status=cached.status,
                website_url=cached.website_url,
                source=cached.source,
                confidence=cached.confidence,
                last_error=cached.error,
                checked_at=_now(),
            )
            report.record(result.status, result.source)
            if result.website_url and (result.status == FOUND):
                _persist_found(connection, lead, result)
            enriched_seeds.append(_seed_with_result(seed, result))
            continue

        result = _enrich_one(lead, config, search, fetch)
        if result.status != FAILED:
            cache.set(
                key,
                CacheEntry(
                    status=result.status,
                    website_url=result.website_url,
                    source=result.source,
                    confidence=result.confidence,
                    error=result.last_error,
                    checked_at=0,
                ),
            )
        if result.website_url and result.status == FOUND:
            _persist_found(connection, lead, result)
        report.record(result.status, result.source)
        enriched_seeds.append(_seed_with_result(seed, result))

    log.info("Enrichment: %s", report.to_log_summary())
    return enriched_seeds, report


def _persist_found(connection: sqlite3.Connection, lead: LeadContext, result: EnrichmentResult) -> None:
    """Ship a verified website to any already-stored no-website lead row.

    Migrates the old ``biz://`` dedupe row in place so re-runs keep a single
    lead per business instead of leaving a stale website-less duplicate. When
    no row exists yet, the pipeline's own upsert creates it from the seed.
    """
    try:
        from src.storage.enrichment import apply_enrichment_to_existing

        apply_enrichment_to_existing(
            connection,
            business_name=lead.business_name,
            city=lead.city,
            state=lead.state,
            category=lead.category,
            website_url=result.website_url,
            source=result.source,
            confidence=result.confidence,
            status=result.status,
            last_error=result.last_error,
            checked_at=result.checked_at,
        )
    except Exception:
        # Never break the run because of a persistence hiccup; the cache +
        # the seed mutation still carry the enrichment forward.
        pass