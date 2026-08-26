from __future__ import annotations

import argparse
import asyncio
import csv
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Optional

try:
    from dotenv import load_dotenv  # type: ignore
except Exception:  # pragma: no cover
    load_dotenv = None  # type: ignore

from src.costing import estimate_cost, pricing_config
from src.contact import ContactSignals, extract_contact_signals_from_crawl
from src.contact.extractor import extract_contact_signals_from_fetch
from src.contact.helpers import google_maps_url as build_google_maps_url
from src.contact.sources import CSV, LLM, pick_across_sources
from src.discovery.discovery import (
    DiscoveryQuery,
    discover_to_seeds,
    load_discovery_queries_csv,
)
from src.discovery.cache import clear_discovery_cache
from src.enrichment.config import from_settings as enrichment_config_from_settings
from src.enrichment.service import run_enrichment
from src.extraction_schema import validate_extracted_lead
from src.fingerprinting.base import PLATFORM_FROM_TECHNOLOGY, Detection
from src.fingerprinting.detector import FingerprintResult, TechnologyDetector, build_site_evidence
from src.fingerprinting.report import summary_csv_fields
from src.llm_extraction import extract_lead_from_fetch, extract_lead_from_merged_content
from src.opportunities import detect_opportunities
from src.opportunities.report import csv_fields_from_rows as opportunity_csv_fields_from_rows
from src.scoring import ScoringInputs, score_lead, score_site_lead
from src.scoring.report import csv_fields_from_row as score_csv_fields_from_row
from src.scraping.focused_crawler import CrawlResult, FocusedCrawler
from src.scraping.page_cache import PageCache
from src.search.config import from_settings as search_config_from_settings
from src.search.search_service import SearchService
from src.seo.report import csv_fields_from_row, to_llm_text
from src.seo.site_audit import audit_site, probe_well_known
from src.settings import (
    CRAWL_CACHE_DIR,
    CRAWL_CACHE_FILE,
    DB_PATH,
    FINGERPRINT_MIN_CONFIDENCE,
    FINGERPRINT_MIN_OVERRIDE_CONFIDENCE,
    SEO_BLEND_WEIGHT,
)
import src.settings as settings_module
from src.storage.db import connect, init_db
from src.storage.leads import LeadUpsert, upsert_lead
from src.storage.normalization import normalize_url_for_dedupe
from src.storage.opportunities import (
    opportunities_for_run as lead_opportunities_for_run,
)
from src.storage.opportunities import replace_opportunities
from src.storage.runs import RunStats, complete_run, start_run, update_run_stats
from src.storage.scores import replace_score as replace_lead_score
from src.storage.scores import scores_for_run as lead_scores_for_run
from src.storage.seo import audits_for_run as seo_audits_for_run
from src.storage.seo import replace_audit as replace_seo_audit
from src.storage.technologies import detections_for_run, get_lead_id_by_url, replace_detections
from src.storage.visual import audits_for_run as visual_audits_for_run
from src.storage.visual import replace_visual_audit
from src.url_loader import SeedRow, load_seed_csv
from src.visual import run_visual_audit
from src.visual.config import from_settings as visual_config_from_settings
from src.visual.report import csv_fields_from_row as visual_csv_fields_from_row
from src.visual.report import to_llm_text as visual_to_llm_text


EXPORT_COLUMNS = [
    "business_name",
    "phone",
    "email",
    "website_url",
    "platform",
    "complexity",
    "load_speed",
    "city",
    "state",
    "category",
    "score",
    "priority",
    "recommendation",
    "cms",
    "frontend_technology",
    "backend_technology",
    "hosting_cdn",
    "analytics",
    "confidence_summary",
    "extraction_success",
    "last_error",
    "site_seo_score",
    "seo_health",
    "seo_issue_summary",
    "pages_with_missing_title",
    "pages_with_missing_meta_description",
    "pages_with_thin_content",
    "pages_with_duplicate_titles",
    "pages_with_images_missing_alt",
    "final_score",
    "priority_label",
    "discovery_quality_score",
    "contactability_score",
    "technical_health_score",
    "seo_health_score",
    "content_strength_score",
    "trust_professionalism_score",
    "outreach_potential_score",
    "top_positive_reasons",
    "top_negative_reasons",
    "recommended_outreach_angle",
    "opportunity_score",
    "opportunity_priority",
    "top_opportunity",
    "recommended_services",
    "business_impact",
    "implementation_effort",
    "opportunity_count",
    "visual_score",
    "visual_health_label",
    "visual_summary",
    "pages_with_weak_mobile_signal",
    "pages_with_clutter_signal",
    "pages_with_weak_cta_signal",
    "pages_with_strong_brand_signal",
    "pages_with_weak_hierarchy_signal",
    "owner_name",
    "postal_code",
    "facebook_url",
    "instagram_url",
    "linkedin_url",
    "twitter_url",
    "youtube_url",
    "whatsapp_url",
    "contact_page_url",
    "contact_form_url",
    "google_maps_url",
    "service_areas",
    "enrichment_status",
    "enrichment_source",
    "enrichment_confidence",
]


def main() -> None:
    if load_dotenv is not None:
        load_dotenv()

    parser = _build_parser()
    args = parser.parse_args()

    if args.limit <= 0:
        raise SystemExit("--limit must be > 0")
    if args.limit > 1000:
        raise SystemExit("--limit is capped at 1000 for safety (v1)")
    if args.max_cost_usd is not None and args.max_cost_usd <= 0:
        raise SystemExit("--max-cost-usd must be > 0")

    logger = _setup_logging(args.log_file)
    logger.info("Starting run")

    if args.clear_cache:
        cleared = clear_discovery_cache()
        logger.info("Cleared discovery cache files: %d", cleared)
        if not args.discover and not args.input and not args.only_failed:
            logger.info("Cache cleared; nothing else to do.")
            return 0

    if args.clear_crawl_cache:
        logger.info("Cleared crawl page cache entries: %d", PageCache(CRAWL_CACHE_DIR, CRAWL_CACHE_FILE).clear())

    if args.rebuild_index and not (args.discover or args.input or args.only_failed):
        stats = _rebuild_search_index(logger)
        logger.info(
            "Search index rebuilt: %d indexed, %d skipped (of %d)",
            stats.indexed,
            stats.skipped,
            stats.total,
        )
        logger.info("Run complete.")
        return

    if args.discover:
        if args.provider == "google":
            logger.warning(
                "Google Places provider is deprecated and requires a paid "
                "GOOGLE_MAPS_API_KEY. Prefer the default 'osm' provider."
            )
        queries = _resolve_discovery_queries(args)
        logger.info("Discovery queries: %d", len(queries))
        for q in queries:
            logger.info("  Discover: %s in %s", q.category, q.location)

        discovered_seeds = discover_to_seeds(
            queries, provider=args.provider, limit=int(args.limit)
        )[: max(0, int(args.limit))]
        logger.info("Discovered seeds: %d", len(discovered_seeds))

        _process_seeds_through_pipeline(
            connection=connect(DB_PATH),
            logger=logger,
            seeds=discovered_seeds,
            args=args,
        )
    elif args.only_failed:
        connection = connect(DB_PATH)
        try:
            init_db(connection)
            seeds = _load_failed_seeds_from_db(connection, limit=int(args.limit))
            logger.info("Failed leads loaded from DB: %d", len(seeds))
            _run_pipeline(connection, logger, seeds, args)
        finally:
            connection.close()
    else:
        if not args.input:
            raise SystemExit("--input is required in CSV mode (or use --discover)")
        input_path = Path(args.input)
        logger.info("Seed CSV: %s", input_path)
        connection = connect(DB_PATH)
        try:
            init_db(connection)
            seeds = load_seed_csv(input_path)[: max(0, int(args.limit))]
            logger.info("Seed rows (after limit): %d", len(seeds))
            _run_pipeline(connection, logger, seeds, args)
        finally:
            connection.close()

    logger.info("Run complete.")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Second Brain Lead Finder (v1)")

    discovery_group = parser.add_argument_group("discovery mode")
    discovery_group.add_argument(
        "--discover",
        action="store_true",
        help="Enable Google Places discovery mode (discover leads automatically)",
    )
    discovery_group.add_argument(
        "--discover-queries",
        default=None,
        help="CSV file with discovery queries (columns: category, location)",
    )
    discovery_group.add_argument(
        "--category",
        default=None,
        help="Business category for inline discovery (e.g. 'plumber')",
    )
    discovery_group.add_argument(
        "--location",
        default=None,
        help="Location for inline discovery (e.g. 'Austin, TX')",
    )
    discovery_group.add_argument(
        "--provider",
        default="osm",
        choices=["osm", "google"],
        help="Discovery source: 'osm' (OpenStreetMap, free, no key) or "
        "'google' (deprecated, requires GOOGLE_MAPS_API_KEY). Default: osm",
    )
    discovery_group.add_argument(
        "--clear-cache",
        action="store_true",
        help="Clear the local discovery cache (geocode + Overpass responses)",
    )

    parser.add_argument("--input", default=None, help="Seed CSV path")
    parser.add_argument("--min-score-export", type=int, default=30)
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument("--max-cost-usd", type=float, default=None)
    parser.add_argument(
        "--only-failed",
        action="store_true",
        help="Ignore input CSV URLs and re-run extraction for failed leads already in the DB",
    )
    parser.add_argument(
        "--log-file",
        default="auto",
        help="Log file path, 'auto' for logs/run_<timestamp>.log, or 'none' to disable",
    )
    parser.add_argument(
        "--no-crawl",
        action="store_true",
        help="Disable focused multi-page crawling; only audit the homepage (v1 behaviour)",
    )
    parser.add_argument(
        "--clear-crawl-cache",
        action="store_true",
        help="Clear the persisted page cache used by the focused crawler",
    )
    parser.add_argument(
        "--rebuild-index",
        action="store_true",
        help="Rebuild the full local semantic search index (after processing, "
        "or standalone when no pipeline mode is given)",
    )
    parser.add_argument(
        "--no-index",
        action="store_true",
        help="Skip incremental search indexing for this run",
    )
    parser.add_argument(
        "--no-enrichment",
        action="store_true",
        help="Skip website enrichment for leads without a website URL "
        "(also skipped automatically with --no-crawl)",
    )
    return parser


def _run_pipeline(connection, logger, seeds: list[SeedRow], args) -> None:
    if args.max_cost_usd is not None:
        pricing = pricing_config()
        if not pricing.enabled:
            raise SystemExit(
                "--max-cost-usd was set, but pricing is not configured. "
                "Set OPENAI_INPUT_COST_PER_1K and/or OPENAI_OUTPUT_COST_PER_1K "
                "(OpenRouter free models are zero-cost by default, so a cost "
                "cap needs explicit per-1K prices)."
            )
        logger.info(
            "Cost stop enabled at $%.4f (prices: input=$%.6f/1K, output=$%.6f/1K)",
            float(args.max_cost_usd),
            pricing.input_cost_per_1k,
            pricing.output_cost_per_1k,
        )

    run_id = start_run(connection)
    seeds = _enrich_seeds_pass(connection, logger, seeds, args)
    stats = _run_seeds(
        connection,
        logger,
        run_id,
        seeds,
        max_cost_usd=args.max_cost_usd,
        crawler=_make_crawler(),
        no_crawl=args.no_crawl,
    )
    update_run_stats(connection, run_id, stats)
    complete_run(connection, run_id)
    export_path = _export_csv_for_run(
        connection,
        run_id=run_id,
        min_score=args.min_score_export,
    )
    logger.info("Run %s complete. Export: %s", run_id, export_path)

    if not args.no_index:
        _index_run_leads(logger, run_id, rebuild=args.rebuild_index)


def _enrich_seeds_pass(connection, logger, seeds: list[SeedRow], args) -> list[SeedRow]:
    """Website enrichment pre-pass: runs before the crawl for website-less seeds.

    Offline runs (--no-crawl) and explicit --no-enrichment skips it entirely.
    A seed with a verified website flows into the normal crawl pipeline; the
    rest stay valid website-less leads with their enrichment status recorded.
    """
    if args.no_crawl or args.no_enrichment:
        return seeds
    config = enrichment_config_from_settings(settings_module)
    if not config.enabled:
        return seeds
    enriched, report = run_enrichment(connection, seeds, config, logger=logger)
    logger.info("Website enrichment: %s", report.to_log_summary())
    return enriched


def _process_seeds_through_pipeline(connection, logger, seeds, args) -> None:
    try:
        init_db(connection)
        _run_pipeline(connection, logger, seeds, args)
    finally:
        connection.close()


def run_discovery_pipeline(
    *,
    category: str,
    location: str,
    limit: int = 50,
    max_cost_usd: Optional[float] = None,
    min_score_export: int = 30,
    provider: str = "osm",
) -> dict[str, Any]:
    """
    Run discovery + scrape + extract + score pipeline inline.
    Returns summary stats.
    """
    logger = logging.getLogger("lead.dashboard")

    queries = [DiscoveryQuery(category=category, location=location)]
    discovered_seeds = discover_to_seeds(queries, provider=provider, limit=int(limit))[
        : max(0, int(limit))
    ]
    logger.info("Discovered %d seeds via provider '%s'", len(discovered_seeds), provider)

    if not discovered_seeds:
        return {"total": 0, "ok": 0, "failed": 0, "cost": 0.0, "seeds": 0}

    connection = connect(DB_PATH)
    try:
        init_db(connection)
        run_id = start_run(connection)
        stats = _run_seeds(
            connection,
            logger,
            run_id,
            discovered_seeds,
            max_cost_usd=max_cost_usd,
        )
        update_run_stats(connection, run_id, stats)
        complete_run(connection, run_id)
        export_path = _export_csv_for_run(
            connection,
            run_id=run_id,
            min_score=min_score_export,
        )
        logger.info("Discovery run %s complete. Export: %s", run_id, export_path)
        return {
            "total": stats.total_urls_processed,
            "ok": stats.successful_extractions,
            "failed": stats.failed_extractions,
            "cost": stats.total_cost_usd,
            "seeds": len(discovered_seeds),
            "run_id": run_id,
            "export": str(export_path),
        }
    finally:
        connection.close()


def _run_seeds(
    connection,
    logger: logging.Logger,
    run_id: int,
    seeds: list[SeedRow],
    *,
    max_cost_usd: Optional[float],
    crawler: Optional[FocusedCrawler] = None,
    no_crawl: bool = False,
) -> RunStats:
    total = 0
    ok = 0
    failed = 0
    total_cost = 0.0

    # Reuse one Playwright instance across URLs (when available).
    async def _async_run() -> None:
        nonlocal total, ok, failed, total_cost

        fetcher_cm = _maybe_playwright_fetcher()
        if fetcher_cm is None:
            logger.warning("Playwright not available; processing as 'no website URL' leads only.")
            for seed in seeds:
                total += 1
                _process_seed_no_fetch(connection, run_id, seed)
                ok += 1
            return

        async with fetcher_cm as fetcher:
            for seed in seeds:
                total += 1

                if max_cost_usd is not None and total_cost >= max_cost_usd:
                    logger.warning(
                        "Stopping early: estimated cost $%.4f >= $%.4f",
                        total_cost,
                        max_cost_usd,
                    )
                    return

                if not seed.url:
                    _process_seed_no_fetch(connection, run_id, seed)
                    ok += 1
                    continue

                fetch = await fetcher.fetch(seed.url)

                # Technology fingerprinting runs on the homepage response only
                # (deterministic, no extra network). When a technology maps to
                # the platform enum with high confidence, it overrides the LLM.
                fingerprint: Optional[FingerprintResult] = None
                platform_override: Optional[str] = None
                try:
                    fingerprint = _fingerprint(fetch)
                    detected_platform = _platform_override(fingerprint)
                    if detected_platform and detected_platform != "unknown":
                        platform_override = detected_platform
                except Exception as exc:  # detector must never break the pipeline
                    logger.debug("Fingerprinting failed for %s: %s", seed.url, exc)

                # Focused multi-page crawl (default), falling back to the
                # homepage-only path whenever a crawl is disabled/unavailable.
                crawl: Optional[CrawlResult] = None
                if crawler is not None and not no_crawl and fetch.success:
                    crawl = await crawler.crawl(fetcher, seed.url, home_fetch=fetch)

                # Deterministic local SEO audit over the already-collected HTML
                # (no extra fetch unless SEO_PROBE_ROBOTS is enabled, no LLM,
                # no paid APIs). The summary is passed to the LLM as neutral
                # context; it never performs SEO detection itself.
                seo_audit = None
                seo_text: Optional[str] = None
                try:
                    seo_probe = (
                        await probe_well_known(fetcher, seed.url) if fetch.success else None
                    )
                    seo_audit = _audit_site_for_seed(seed, fetch, crawl, probe=seo_probe)
                    seo_text = to_llm_text(seo_audit) if seo_audit is not None else None
                    if seo_audit is not None:
                        logger.info(
                            "SEO audit for %s: %d/100 (%s, %d pages)",
                            seed.url,
                            seo_audit.site_score,
                            seo_audit.overall_health,
                            seo_audit.total_pages_audited,
                        )
                except Exception as exc:  # audit must never break the pipeline
                    logger.debug("SEO audit failed for %s: %s", seed.url, exc)

                # Local visual website audit: bounded screenshots + deterministic
                # computer-vision-lite heuristics (no LLM unless VISUAL_LLM_ENABLED).
                # The neutral banner text reaches the LLM as context only.
                visual_audit = None
                visual_text: Optional[str] = None
                visual_config = visual_config_from_settings(settings_module)
                try:
                    if visual_config.enabled and fetch.success:
                        visual_audit = await run_visual_audit(
                            fetcher,
                            seed.url,
                            _crawl_summary(crawl),
                            (
                                [d.to_dict() for d in fingerprint.detections]
                                if fingerprint and fingerprint.detections
                                else []
                            ),
                            visual_config,
                            page_context=_visual_page_context(seed, crawl, seo_audit),
                        )
                        visual_text = (
                            visual_to_llm_text(visual_audit)
                            if visual_audit is not None
                            else None
                        )
                        if visual_audit is not None:
                            logger.info(
                                "Visual audit for %s: %d/100 (%s, %d pages)",
                                seed.url,
                                visual_audit.visual_score,
                                visual_audit.visual_health_label,
                                visual_audit.total_pages_audited,
                            )
                except Exception as exc:  # audit must never break the pipeline
                    logger.debug("Visual audit failed for %s: %s", seed.url, exc)

                if crawl is not None and crawl.ok and crawl.merged_text.strip():
                    logger.info(
                        "Sending merged content (%d chars, %d pages) to LLM for %s",
                        len(crawl.merged_text),
                        len(crawl.pages),
                        seed.url,
                    )
                    extracted = _extract_from_crawl(
                        seed,
                        crawl,
                        fingerprint=fingerprint,
                        detected_seo_text=seo_text,
                        detected_visual_text=visual_text,
                    )
                else:
                    logger.info(
                        "Crawl produced no usable content for %s; using homepage only",
                        seed.url,
                    )
                    extracted = _extract_from_fetch(
                        seed,
                        fetch,
                        fingerprint=fingerprint,
                        detected_seo_text=seo_text,
                        detected_visual_text=visual_text,
                    )

                if platform_override:
                    extracted["platform"] = platform_override

                # Deterministic multi-dimensional scoring. Pure local logic
                # over already-collected signals; the LLM never scores leads.
                signals = ScoringInputs(
                    extracted=extracted,
                    business_name=extracted.get("business_name") or seed.business_name or None,
                    category=seed.category or None,
                    city=seed.city or None,
                    state=seed.state or None,
                    address=seed.address or None,
                    source=seed.source or None,
                    osm_id=seed.osm_id or None,
                    website_url=seed.url or None,
                    fetch_ok=fetch.success,
                    last_error=extracted.get("last_error"),
                    detections=(
                        [d.to_dict() for d in fingerprint.detections]
                        if fingerprint and fingerprint.detections
                        else None
                    ),
                    crawl=_crawl_summary(crawl),
                    seo_audit=seo_audit.to_dict() if seo_audit is not None else None,
                    visual_audit=(
                        visual_audit.to_dict() if visual_audit is not None else None
                    ),
                )
                lead_score = None
                try:
                    lead_score = score_site_lead(signals)
                    logger.info(
                        "Scored %s: %d/100 (%s)",
                        seed.url,
                        lead_score.final_score,
                        lead_score.priority_label,
                    )
                except Exception as exc:  # scoring must never break the pipeline
                    logger.debug("Scoring failed for %s: %s", seed.url, exc)
                    fallback = score_lead(extracted, site_seo_score=seo_audit.site_score if seo_audit is not None else None, seo_blend_weight=SEO_BLEND_WEIGHT)
                    lead_score = _fallback_lead_score(fallback)

                # Deterministic business opportunity detection. Same pure
                # local model over the same signals; never breaks the
                # pipeline and never uses the LLM.
                opportunity_report = None
                try:
                    opportunity_report = detect_opportunities(
                        signals, lead_score=lead_score
                    )
                    logger.info(
                        "Opportunities for %s: %d (top: %s, %d/100)",
                        seed.url,
                        opportunity_report.opportunity_count,
                        opportunity_report.top_opportunity or "none",
                        opportunity_report.top_opportunity_score,
                    )
                except Exception as exc:
                    logger.debug("Opportunity detection failed for %s: %s", seed.url, exc)

                contact = _build_contact_fields(seed, fetch, crawl, extracted)

                phone, phone_source, phone_confidence = pick_across_sources(
                    (contact["phone"], contact["phone_source"], contact["phone_confidence"]),
                    (extracted.get("phone"), LLM, None),
                    (seed.phone, CSV, None),
                )
                email, email_source, email_confidence = pick_across_sources(
                    (contact["email"], contact["email_source"], contact["email_confidence"]),
                    (extracted.get("email"), LLM, None),
                    (seed.email, CSV, None),
                )

                lead = LeadUpsert(
                    website_url=seed.url,
                    business_name=extracted.get("business_name") or seed.business_name or None,
                    phone=phone,
                    email=email,
                    phone_source=phone_source,
                    email_source=email_source,
                    phone_confidence=phone_confidence,
                    email_confidence=email_confidence,
                    platform=extracted.get("platform"),
                    complexity=extracted.get("complexity"),
                    load_speed=extracted.get("load_speed"),
                    city=seed.city or None,
                    state=seed.state or None,
                    category=seed.category or None,
                    score=lead_score.final_score,
                    priority=lead_score.priority_label,
                    extraction_success=bool(extracted.get("extraction_success")),
                    last_error=extracted.get("last_error"),
                    run_id=run_id,
                    source=seed.source,
                    osm_id=seed.osm_id,
                    osm_type=seed.osm_type,
                    latitude=seed.latitude,
                    longitude=seed.longitude,
                    address=contact["address"],
                    opening_hours=contact["opening_hours"],
                    country=contact["country"],
                    owner_name=contact["owner_name"],
                    postal_code=contact["postal_code"],
                    facebook_url=contact["facebook_url"],
                    instagram_url=contact["instagram_url"],
                    linkedin_url=contact["linkedin_url"],
                    twitter_url=contact["twitter_url"],
                    youtube_url=contact["youtube_url"],
                    whatsapp_url=contact["whatsapp_url"],
                    contact_page_url=contact["contact_page_url"],
                    contact_form_url=contact["contact_form_url"],
                    google_maps_url=contact["google_maps_url"],
                    service_areas=contact["service_areas"],
                    enrichment_status=seed.enrichment_status,
                    enrichment_source=seed.enrichment_source,
                    enrichment_confidence=seed.enrichment_confidence,
                    enrichment_last_error=seed.enrichment_last_error,
                    enrichment_last_checked_at=seed.enrichment_last_checked_at,
                )

                try:
                    upsert_lead(connection, lead)
                    ok += 1
                except Exception as exc:
                    failed += 1
                    logger.error("[FAIL] upsert %s: %s", seed.url, exc)

                if fingerprint and fingerprint.detections:
                    try:
                        normalized = normalize_url_for_dedupe(seed.url) if seed.url else ""
                        lead_id = get_lead_id_by_url(connection, normalized) if normalized else None
                        if lead_id is not None:
                            replace_detections(connection, lead_id, list(fingerprint.detections))
                    except Exception as exc:
                        logger.debug("Could not persist detections for %s: %s", seed.url, exc)

                if seo_audit is not None:
                    try:
                        normalized = normalize_url_for_dedupe(seed.url) if seed.url else ""
                        lead_id = get_lead_id_by_url(connection, normalized) if normalized else None
                        if lead_id is not None:
                            site_dict = seo_audit.to_dict()
                            page_dicts = site_dict.pop("pages")
                            replace_seo_audit(connection, lead_id, site_dict, page_dicts)
                    except Exception as exc:
                        logger.debug("Could not persist SEO audit for %s: %s", seed.url, exc)

                if visual_audit is not None:
                    try:
                        normalized = normalize_url_for_dedupe(seed.url) if seed.url else ""
                        lead_id = get_lead_id_by_url(connection, normalized) if normalized else None
                        if lead_id is not None:
                            site_dict = visual_audit.to_dict()
                            page_dicts = site_dict.pop("pages")
                            replace_visual_audit(connection, lead_id, site_dict, page_dicts)
                    except Exception as exc:
                        logger.debug("Could not persist visual audit for %s: %s", seed.url, exc)

                if lead_score is not None:
                    try:
                        normalized = normalize_url_for_dedupe(seed.url) if seed.url else ""
                        lead_id = get_lead_id_by_url(connection, normalized) if normalized else None
                        if lead_id is not None:
                            replace_lead_score(connection, lead_id, lead_score)
                    except Exception as exc:
                        logger.debug("Could not persist score for %s: %s", seed.url, exc)

                if opportunity_report is not None and opportunity_report.opportunities:
                    try:
                        normalized = normalize_url_for_dedupe(seed.url) if seed.url else ""
                        lead_id = get_lead_id_by_url(connection, normalized) if normalized else None
                        if lead_id is not None:
                            replace_opportunities(connection, lead_id, opportunity_report)
                    except Exception as exc:
                        logger.debug("Could not persist opportunities for %s: %s", seed.url, exc)

                usage = extracted.get("_usage")
                cost = estimate_cost(usage) if usage is not None else None
                if cost is not None:
                    total_cost += cost.total_cost_usd

                # Periodic progress.
                if total % 10 == 0:
                    logger.info(
                        "Processed %d/%d (ok=%d, failed=%d, cost=$%.4f)",
                        total,
                        len(seeds),
                        ok,
                        failed,
                        total_cost,
                    )

    asyncio.run(_async_run())
    logger.info(
        "Finished URLs=%d ok=%d failed=%d estimated_cost=$%.4f",
        total,
        ok,
        failed,
        total_cost,
    )
    return RunStats(
        total_urls_processed=total,
        successful_extractions=ok,
        failed_extractions=failed,
        total_cost_usd=round(float(total_cost), 6),
    )


def _maybe_playwright_fetcher():
    try:
        # Only enable fetching if Playwright runtime is available.
        from playwright.async_api import async_playwright  # type: ignore  # noqa: F401
    except Exception:
        return None

    from src.scraping.browser_fetch import PlaywrightFetcher

    return PlaywrightFetcher()


def _make_crawler() -> FocusedCrawler:
    return FocusedCrawler()


def _fingerprint(fetch) -> FingerprintResult:
    """Run the deterministic technology detector over a homepage response."""
    evidence = build_site_evidence(
        html=fetch.html,
        headers=fetch.headers or None,
        cookies=fetch.cookies or None,
    )
    return TechnologyDetector(min_confidence=FINGERPRINT_MIN_CONFIDENCE).detect(
        evidence, site_url=fetch.final_url or fetch.url
    )


def _platform_override(fingerprint: FingerprintResult) -> Optional[str]:
    """Highest-confidence platform enum (if confident enough), else None."""
    best: Optional[str] = None
    best_conf = 0
    for detection in fingerprint.detections:
        mapped = PLATFORM_FROM_TECHNOLOGY.get(detection.name)
        if mapped and detection.confidence > best_conf:
            best, best_conf = mapped, detection.confidence
    if best_conf >= FINGERPRINT_MIN_OVERRIDE_CONFIDENCE:
        return best
    return None


def _tech_banner(fingerprint: Optional[FingerprintResult]) -> Optional[str]:
    """LLM banner text when the detector produced detections (else None)."""
    if fingerprint is None:
        return None
    from src.fingerprinting.report import to_llm_text

    text = to_llm_text(fingerprint)
    return text if fingerprint.detections else None


def _audit_site_for_seed(seed: SeedRow, fetch, crawl: Optional[CrawlResult], *, probe=None):
    """Run the deterministic SEO audit over crawl pages, or the homepage only.

    Returns None when there is nothing to audit (failed fetch / empty HTML).
    """
    if crawl is not None and crawl.ok and crawl.pages:
        return audit_site(crawl.pages, crawl.url, probe=probe)
    if fetch.success and (fetch.html or "").strip():
        home = SimpleNamespace(
            url=fetch.final_url or fetch.url,
            label="HOME",
            title="",
            text=fetch.text or "",
            html=fetch.html or "",
        )
        return audit_site([home], home.url, probe=probe)
    return None


def _process_seed_no_fetch(connection, run_id: int, seed: SeedRow) -> None:
    # Website identity is input data: preserve it even when nothing can be
    # fetched. A crawl failure (or missing Playwright) must never demote a
    # valid seed URL to "no website" — that would destroy dedupe identity,
    # lose derived-intelligence joins and create duplicates on later runs.
    if getattr(seed, "url_error", None):
        no_fetch_error = seed.url_error or ""
    elif seed.url:
        no_fetch_error = "Playwright unavailable; website not fetched"
    else:
        no_fetch_error = "No website URL provided"
    extracted = validate_extracted_lead(
        {
            "url": seed.url or None,
            "business_name": seed.business_name or None,
            "phone": seed.phone,
            "email": seed.email,
            "platform": "unknown",
            "complexity": "unknown",
            "load_speed": "unknown",
            "extraction_success": False,
            "last_error": no_fetch_error,
        }
    ).to_dict()

    lead_score = score_site_lead(
        ScoringInputs(
            extracted=extracted,
            business_name=seed.business_name or None,
            category=seed.category or None,
            city=seed.city or None,
            state=seed.state or None,
            address=seed.address or None,
            source=seed.source or None,
            osm_id=seed.osm_id or None,
            # Preserve identity for scoring; fetch_ok stays False because no
            # crawl ran (website existence ≠ crawl success).
            website_url=seed.url or None,
            fetch_ok=False,
        )
    )

    contact = _build_contact_fields(seed, fetch=None, crawl=None, extracted=extracted)

    lead = LeadUpsert(
        website_url=seed.url or None,
        business_name=seed.business_name or None,
        phone=seed.phone,
        email=seed.email,
        phone_source=CSV if seed.phone else None,
        email_source=CSV if seed.email else None,
        platform=extracted.get("platform"),
        complexity=extracted.get("complexity"),
        load_speed=extracted.get("load_speed"),
        city=seed.city or None,
        state=seed.state or None,
        category=seed.category or None,
        score=lead_score.final_score,
        priority=lead_score.priority_label,
        extraction_success=False,
        last_error=extracted.get("last_error"),
        run_id=run_id,
        source=seed.source,
        osm_id=seed.osm_id,
        osm_type=seed.osm_type,
        latitude=seed.latitude,
        longitude=seed.longitude,
        address=contact["address"],
        opening_hours=contact["opening_hours"],
        country=contact["country"],
        owner_name=contact["owner_name"],
        postal_code=contact["postal_code"],
        facebook_url=contact["facebook_url"],
        instagram_url=contact["instagram_url"],
        linkedin_url=contact["linkedin_url"],
        twitter_url=contact["twitter_url"],
        youtube_url=contact["youtube_url"],
        whatsapp_url=contact["whatsapp_url"],
        contact_page_url=contact["contact_page_url"],
        contact_form_url=contact["contact_form_url"],
        google_maps_url=contact["google_maps_url"],
        service_areas=contact["service_areas"],
        enrichment_status=seed.enrichment_status,
        enrichment_source=seed.enrichment_source,
        enrichment_confidence=seed.enrichment_confidence,
        enrichment_last_error=seed.enrichment_last_error,
        enrichment_last_checked_at=seed.enrichment_last_checked_at,
    )

    try:
        normalized = upsert_lead(connection, lead)
        lead_id = get_lead_id_by_url(connection, normalized) if normalized else None
        if lead_id is not None:
            replace_lead_score(connection, lead_id, lead_score)
    except Exception as exc:
        logger = logging.getLogger("lead")
        logger.debug("Could not persist score for no-website lead: %s", exc)


def _crawl_summary(crawl: Optional[CrawlResult]) -> Optional[dict]:
    """Flatten a CrawlResult into the structured dict the scorer consumes."""
    if crawl is None:
        return None
    return {
        "ok": bool(crawl.ok),
        "error": crawl.error,
        "merged_text": crawl.merged_text,
        "contact_clues": list(crawl.contact_clues),
        "social_urls": list(crawl.contact_signals.social_urls),
        "pages": [
            {"url": page.url, "label": page.label, "title": page.title, "text": page.text}
            for page in crawl.pages
        ],
    }


def _build_contact_fields(
    seed: SeedRow,
    fetch,
    crawl: Optional[CrawlResult],
    extracted: dict,
) -> dict:
    """Merge contact intelligence signals into the lead row fields.

    Priority: crawl signals > homepage-only signals > discovery fields. A
    valid existing value is never overwritten by an empty one; the Google
    Maps URL is derived locally from seed coordinates (no API calls).
    Best-effort: any failure degrades to the discovery fields only.
    """
    signals = ContactSignals()
    try:
        if crawl is not None and crawl.ok:
            signals = extract_contact_signals_from_crawl(crawl, website_url=seed.url)
        elif fetch is not None:
            signals = extract_contact_signals_from_fetch(fetch)
    except Exception as exc:
        logging.getLogger("lead").debug(
            "Contact extraction failed for %s: %s", seed.url, exc
        )

    return {
        "phone": signals.phone or None,
        "email": signals.email or None,
        "address": signals.address or seed.address or None,
        "country": signals.country or seed.country or None,
        "opening_hours": signals.opening_hours or seed.opening_hours or None,
        "postal_code": signals.postal_code or seed.postal_code or None,
        "owner_name": signals.owner_name,
        "facebook_url": signals.facebook_url,
        "instagram_url": signals.instagram_url,
        "linkedin_url": signals.linkedin_url,
        "twitter_url": signals.twitter_url,
        "youtube_url": signals.youtube_url,
        "whatsapp_url": signals.whatsapp_url,
        "contact_page_url": signals.contact_page_url,
        "contact_form_url": signals.contact_form_url,
        "google_maps_url": signals.google_maps_url
        or build_google_maps_url(seed.latitude, seed.longitude),
        "service_areas": signals.service_areas or None,
        "phone_source": signals.phone_source,
        "email_source": signals.email_source,
        "phone_confidence": signals.phone_confidence,
        "email_confidence": signals.email_confidence,
    }


def _visual_page_context(
    seed: SeedRow,
    crawl: Optional[CrawlResult],
    seo_audit,
) -> dict[str, dict]:
    """Map page URL -> text-derived signals for the visual audit.

    Combines SEO audit per-page signals (word_count, image_count) with crawl
    page titles so the visual heuristics can enrich pixel-only evidence without
    any extra network access. Best-effort: unknown URLs simply get no context
    and the associated signal degrades gracefully.
    """
    context: dict[str, dict] = {}
    if seo_audit is not None:
        for page in seo_audit.pages:
            context[page.url] = {
                "word_count": int(page.word_count or 0),
                "image_count": int(page.image_count or 0),
            }
    if crawl is not None and crawl.pages:
        for crawl_page in crawl.pages:
            entry = context.setdefault(crawl_page.url, {})
            entry.setdefault("title", crawl_page.title)
            if crawl_page.text:
                entry.setdefault("word_count", len(crawl_page.text.split()))
    if seed.url and seed.url not in context and crawl is not None and crawl.pages:
        context[seed.url] = context.get(crawl.pages[0].url, {})
    return context


def _fallback_lead_score(fallback) -> "LeadScore":
    """Convert the legacy ScoreResult into a LeadScore for the columns.

    Used only if the deterministic engine itself raises (should not happen);
    keeps the pipeline running with backward-compatible values.
    """
    from src.scoring.base import LeadScore

    return LeadScore(
        final_score=fallback.score,
        priority_label=fallback.priority,
        dimension_scores={},
        dimension_reasons={},
        top_positive_reasons=fallback.reasons,
        top_negative_reasons=[],
        recommended_outreach_angle=fallback.recommendation,
    )


def _extract_from_fetch(
    seed: SeedRow,
    fetch,
    fingerprint: Optional[FingerprintResult] = None,
    detected_seo_text: Optional[str] = None,
    detected_visual_text: Optional[str] = None,
) -> dict:
    if not fetch.success:
        # Loggable error text is stored in last_error.
        return validate_extracted_lead(
            {
                "url": fetch.final_url or fetch.url,
                "business_name": seed.business_name or None,
                "phone": None,
                "email": None,
                "platform": "unknown",
                "complexity": "unknown",
                "load_speed": "unknown",
                "extraction_success": False,
                "last_error": fetch.error or "Fetch failed",
            }
        ).to_dict()

    try:
        result = extract_lead_from_fetch(
            fetch,
            detected_technology_text=_tech_banner(fingerprint),
            detected_seo_text=detected_seo_text,
            detected_visual_text=detected_visual_text,
        )
        payload = result.lead.to_dict()
        # Attach usage for cost tracking without storing it in DB.
        payload["_usage"] = result.usage
        if not payload.get("business_name"):
            payload["business_name"] = seed.business_name or None
        return payload
    except Exception as exc:
        return validate_extracted_lead(
            {
                "url": fetch.final_url or fetch.url,
                "business_name": seed.business_name or None,
                "phone": None,
                "email": None,
                "platform": "unknown",
                "complexity": "unknown",
                "load_speed": "unknown",
                "extraction_success": False,
                "last_error": f"LLM extraction failed: {exc}",
            }
        ).to_dict()


def _extract_from_crawl(
    seed: SeedRow,
    crawl: CrawlResult,
    fingerprint: Optional[FingerprintResult] = None,
    detected_seo_text: Optional[str] = None,
    detected_visual_text: Optional[str] = None,
) -> dict:
    try:
        result = extract_lead_from_merged_content(
            crawl.merged_text,
            source_url=crawl.url,
            contact_clues=list(crawl.contact_clues),
            detected_technology_text=_tech_banner(fingerprint),
            detected_seo_text=detected_seo_text,
            detected_visual_text=detected_visual_text,
        )
        payload = result.lead.to_dict()
        # Attach usage to the payload for cost tracking without storing it in DB.
        payload["_usage"] = result.usage
        if not payload.get("business_name"):
            payload["business_name"] = seed.business_name or None
        return payload
    except Exception as exc:
        return validate_extracted_lead(
            {
                "url": crawl.url,
                "business_name": seed.business_name or None,
                "phone": None,
                "email": None,
                "platform": "unknown",
                "complexity": "unknown",
                "load_speed": "unknown",
                "extraction_success": False,
                "last_error": f"LLM extraction failed (crawl): {exc}",
            }
        ).to_dict()


def _export_csv_for_run(connection, *, run_id: int, min_score: int) -> Path:
    exports_dir = Path("exports")
    exports_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = exports_dir / f"leads_{ts}.csv"

    rows = connection.execute(
        """
        SELECT
          business_name, phone, email, website_url, website_url_normalized,
          platform, complexity, load_speed,
          city, state, category,
          score, priority,
          extraction_success, last_error,
          address, country, opening_hours, postal_code, owner_name,
          facebook_url, instagram_url, linkedin_url, twitter_url, youtube_url,
          whatsapp_url, contact_page_url, contact_form_url, google_maps_url,
          service_areas_json,
          enrichment_status, enrichment_source, enrichment_confidence
        FROM leads
        WHERE run_id = ? AND (score IS NOT NULL AND score >= ?)
        ORDER BY score DESC, extracted_at DESC
        """,
        (run_id, int(min_score)),
    ).fetchall()

    # Merge per-lead technology fingerprint summary (all detections for the run).
    lead_id_map: dict[int, list[Detection]] = {}
    for row in detections_for_run(connection, run_id):
        lead_id = int(row["lead_id"])
        lead_id_map.setdefault(lead_id, []).append(
            Detection(
                name=row["technology_name"],
                category=row["category"],
                confidence=int(row["confidence"]),
                evidence=tuple(row["evidence"] or []),
            )
        )
    tech_by_lead: dict[int, dict] = {
        lead_id: summary_csv_fields(FingerprintResult(detections=tuple(items), site_url=None))
        for lead_id, items in lead_id_map.items()
    }

    # lead_id by website_url_normalized for joining tech summaries.
    lead_id_by_normalized: dict[str, int] = {}
    for lead in connection.execute("SELECT id, website_url_normalized FROM leads WHERE run_id = ?", (run_id,)):
        lead_id_by_normalized[str(lead["website_url_normalized"])] = int(lead["id"])

    # Merge per-lead site-level SEO audit summaries.
    seo_by_lead: dict[int, dict] = {
        int(row["lead_id"]): row for row in seo_audits_for_run(connection, run_id)
    }

    # Merge per-lead deterministic multi-dimensional score rows.
    score_by_lead: dict[int, dict] = {
        int(row["lead_id"]): row for row in lead_scores_for_run(connection, run_id)
    }

    # Merge per-lead detected business opportunities.
    opportunities_by_lead: dict[int, list[dict]] = {}
    for row in lead_opportunities_for_run(connection, run_id):
        opportunities_by_lead.setdefault(int(row["lead_id"]), []).append(row)

    # Merge per-lead site-level visual audit summaries.
    visual_by_lead: dict[int, dict] = {
        int(row["lead_id"]): row for row in visual_audits_for_run(connection, run_id)
    }

    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=EXPORT_COLUMNS)
        writer.writeheader()
        for row in rows:
            record = dict(row)
            # Decode the JSON-encoded service areas into a flat list column.
            try:
                areas = json.loads(record.get("service_areas_json") or "[]")
                record["service_areas"] = "; ".join(str(area) for area in areas)
            except ValueError:
                record["service_areas"] = record.get("service_areas_json") or ""
            # Add recommendation at export-time (not stored in DB).
            score = score_lead(
                {
                    "website_url": record.get("website_url") or "",
                    "platform": record.get("platform"),
                    "load_speed": record.get("load_speed"),
                    "complexity": record.get("complexity"),
                    "phone": record.get("phone") or "",
                    "email": record.get("email") or "",
                }
            )
            record["recommendation"] = score.recommendation
            record["extraction_success"] = bool(record.get("extraction_success"))
            record["cms"] = ""
            record["frontend_technology"] = ""
            record["backend_technology"] = ""
            record["hosting_cdn"] = ""
            record["analytics"] = ""
            record["confidence_summary"] = ""
            record["site_seo_score"] = ""
            record["seo_health"] = ""
            record["seo_issue_summary"] = ""
            record["pages_with_missing_title"] = ""
            record["pages_with_missing_meta_description"] = ""
            record["pages_with_thin_content"] = ""
            record["pages_with_duplicate_titles"] = ""
            record["pages_with_images_missing_alt"] = ""
            record["final_score"] = ""
            record["priority_label"] = ""
            record["discovery_quality_score"] = ""
            record["contactability_score"] = ""
            record["technical_health_score"] = ""
            record["seo_health_score"] = ""
            record["content_strength_score"] = ""
            record["trust_professionalism_score"] = ""
            record["outreach_potential_score"] = ""
            record["top_positive_reasons"] = ""
            record["top_negative_reasons"] = ""
            record["recommended_outreach_angle"] = ""
            record["opportunity_score"] = ""
            record["opportunity_priority"] = ""
            record["top_opportunity"] = ""
            record["recommended_services"] = ""
            record["business_impact"] = ""
            record["implementation_effort"] = ""
            record["opportunity_count"] = ""
            record["visual_score"] = ""
            record["visual_health_label"] = ""
            record["visual_summary"] = ""
            record["pages_with_weak_mobile_signal"] = ""
            record["pages_with_clutter_signal"] = ""
            record["pages_with_weak_cta_signal"] = ""
            record["pages_with_strong_brand_signal"] = ""
            record["pages_with_weak_hierarchy_signal"] = ""
            # Match the lead by its PERSISTED identity: the stored
            # website_url_normalized covers both URL-keyed rows and synthetic
            # biz:// rows; a derived normalization of website_url is only a
            # fallback for legacy rows. Joining on normalize(website_url)
            # alone strands every no-website lead's derived columns (H-10).
            normalized = (
                record.get("website_url_normalized")
                or normalize_url_for_dedupe(record.get("website_url") or "")
            )
            lead_id = lead_id_by_normalized.get(normalized)
            if lead_id is not None:
                for key, value in tech_by_lead.get(lead_id, {}).items():
                    record[key] = value
                seo_row = seo_by_lead.get(lead_id)
                if seo_row is not None:
                    for key, value in csv_fields_from_row(seo_row).items():
                        record[key] = value
                score_row = score_by_lead.get(lead_id)
                if score_row is not None:
                    for key, value in score_csv_fields_from_row(score_row).items():
                        record[key] = value
                    record["recommendation"] = record["recommended_outreach_angle"]
                opportunity_rows = opportunities_by_lead.get(lead_id)
                if opportunity_rows:
                    for key, value in opportunity_csv_fields_from_rows(opportunity_rows).items():
                        record[key] = value
                visual_row = visual_by_lead.get(lead_id)
                if visual_row is not None:
                    for key, value in visual_csv_fields_from_row(visual_row).items():
                        record[key] = value
            writer.writerow({k: record.get(k) for k in EXPORT_COLUMNS})

    return out_path


def _index_run_leads(logger, run_id: int, *, rebuild: bool = False) -> None:
    """Incrementally update the local semantic search index for a pipeline run.

    Indexing is a best-effort stage: any failure is logged and never breaks the
    run. Content-hash diffing means unchanged leads are skipped without any
    embedding work (see src/search/search_service.py).
    """
    try:
        config = search_config_from_settings(settings_module)
        if not config.enabled:
            logger.info("Search indexing disabled (SEARCH_ENABLED=0); skipping")
            return
        service = SearchService(DB_PATH, config=config)
        stats = service.rebuild_index() if rebuild else service.index_run(run_id)
        logger.info(
            "Search index for run %s: %d indexed, %d skipped (of %d) via %s",
            run_id,
            stats.indexed,
            stats.skipped,
            stats.total,
            service.embedder.name,
        )
    except Exception as exc:
        logger.debug("Search indexing failed for run %s: %s", run_id, exc)


def _rebuild_search_index(logger):
    """Rebuild the entire search index (all leads in the database)."""
    config = search_config_from_settings(settings_module)
    if not config.enabled:
        logger.info("Search indexing disabled (SEARCH_ENABLED=0); skipping")
        from src.search.search_service import IndexStats

        return IndexStats(total=0, indexed=0, skipped=0)
    return SearchService(DB_PATH, config=config).rebuild_index()


def _load_failed_seeds_from_db(connection, *, limit: int) -> list[SeedRow]:
    """
    Load previously-failed leads from the DB as seeds for a re-run.
    """

    rows = connection.execute(
        """
        SELECT business_name, category, website_url AS url, city, state
        FROM leads
        WHERE (extraction_success = 0 OR last_error IS NOT NULL)
          AND website_url IS NOT NULL
        ORDER BY extracted_at DESC
        LIMIT ?
        """,
        (int(limit),),
    ).fetchall()

    seeds: list[SeedRow] = []
    for row in rows:
        seeds.append(
            SeedRow(
                business_name=row["business_name"] or "",
                category=row["category"] or "",
                url=row["url"],
                city=row["city"] or "",
                state=row["state"] or "",
            )
        )
    return seeds


def _resolve_discovery_queries(args) -> list[DiscoveryQuery]:
    if args.discover_queries:
        path = Path(args.discover_queries)
        return load_discovery_queries_csv(path)
    if args.category and args.location:
        return [DiscoveryQuery(category=args.category, location=args.location)]
    raise SystemExit(
        "Discovery mode requires either --discover-queries <csv> or "
        "--category <cat> --location <loc>."
    )


def _setup_logging(log_file: str) -> logging.Logger:
    logger = logging.getLogger("lead")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")

    sh = logging.StreamHandler(stream=sys.stdout)
    sh.setLevel(logging.INFO)
    sh.setFormatter(formatter)
    logger.addHandler(sh)

    log_file_clean = (log_file or "").strip().lower()
    if log_file_clean and log_file_clean != "none":
        if log_file_clean == "auto":
            logs_dir = Path("logs")
            logs_dir.mkdir(parents=True, exist_ok=True)
            path = logs_dir / f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        else:
            path = Path(log_file)
            path.parent.mkdir(parents=True, exist_ok=True)

        fh = logging.FileHandler(path, encoding="utf-8")
        fh.setLevel(logging.INFO)
        fh.setFormatter(formatter)
        logger.addHandler(fh)
        logger.info("Logging to %s", path)

    return logger


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
