from __future__ import annotations

import argparse
import asyncio
import csv
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

try:
    from dotenv import load_dotenv  # type: ignore
except Exception:  # pragma: no cover
    load_dotenv = None  # type: ignore

from src.costing import estimate_cost, pricing_config
from src.discovery.discovery import (
    DiscoveryQuery,
    discover_to_seeds,
    load_discovery_queries_csv,
)
from src.extraction_schema import validate_extracted_lead
from src.llm_extraction import extract_lead_from_fetch
from src.scoring import score_lead
from src.settings import DB_PATH
from src.storage.db import connect, init_db
from src.storage.leads import LeadUpsert, upsert_lead
from src.storage.runs import RunStats, complete_run, start_run, update_run_stats
from src.url_loader import SeedRow, load_seed_csv


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
    "extraction_success",
    "last_error",
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

    if args.discover:
        queries = _resolve_discovery_queries(args)
        logger.info("Discovery queries: %d", len(queries))
        for q in queries:
            logger.info("  Discover: %s in %s", q.category, q.location)

        discovered_seeds = discover_to_seeds(queries)[: max(0, int(args.limit))]
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
    return parser


def _run_pipeline(connection, logger, seeds: list[SeedRow], args) -> None:
    if args.max_cost_usd is not None:
        pricing = pricing_config()
        if not pricing.enabled:
            raise SystemExit(
                "--max-cost-usd was set, but pricing is not configured. "
                "Set OPENAI_INPUT_COST_PER_1K and/or OPENAI_OUTPUT_COST_PER_1K."
            )
        logger.info(
            "Cost stop enabled at $%.4f (prices: input=$%.6f/1K, output=$%.6f/1K)",
            float(args.max_cost_usd),
            pricing.input_cost_per_1k,
            pricing.output_cost_per_1k,
        )

    run_id = start_run(connection)
    stats = _run_seeds(
        connection,
        logger,
        run_id,
        seeds,
        max_cost_usd=args.max_cost_usd,
    )
    update_run_stats(connection, run_id, stats)
    complete_run(connection, run_id)
    export_path = _export_csv_for_run(
        connection,
        run_id=run_id,
        min_score=args.min_score_export,
    )
    logger.info("Run %s complete. Export: %s", run_id, export_path)


def _process_seeds_through_pipeline(connection, logger, seeds, args) -> None:
    try:
        init_db(connection)
        _run_pipeline(connection, logger, seeds, args)
    finally:
        connection.close()


def _run_seeds(
    connection,
    logger: logging.Logger,
    run_id: int,
    seeds: list[SeedRow],
    *,
    max_cost_usd: Optional[float],
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
                extracted = _extract_from_fetch(seed, fetch)
                score = score_lead(extracted)

                lead = LeadUpsert(
                    website_url=seed.url,
                    business_name=extracted.get("business_name") or seed.business_name or None,
                    phone=extracted.get("phone"),
                    email=extracted.get("email"),
                    platform=extracted.get("platform"),
                    complexity=extracted.get("complexity"),
                    load_speed=extracted.get("load_speed"),
                    city=seed.city or None,
                    state=seed.state or None,
                    category=seed.category or None,
                    score=score.score,
                    priority=score.priority,
                    extraction_success=bool(extracted.get("extraction_success")),
                    last_error=extracted.get("last_error"),
                    run_id=run_id,
                )

                try:
                    upsert_lead(connection, lead)
                    ok += 1
                except Exception as exc:
                    failed += 1
                    logger.error("[FAIL] upsert %s: %s", seed.url, exc)

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


def _process_seed_no_fetch(connection, run_id: int, seed: SeedRow) -> None:
    extracted = validate_extracted_lead(
        {
            "url": None,
            "business_name": seed.business_name or None,
            "phone": None,
            "email": None,
            "platform": "unknown",
            "complexity": "unknown",
            "load_speed": "unknown",
            "extraction_success": False,
            "last_error": "No website URL provided",
        }
    ).to_dict()
    score = score_lead(extracted)

    lead = LeadUpsert(
        website_url=None,
        business_name=seed.business_name or None,
        phone=None,
        email=None,
        platform=extracted.get("platform"),
        complexity=extracted.get("complexity"),
        load_speed=extracted.get("load_speed"),
        city=seed.city or None,
        state=seed.state or None,
        category=seed.category or None,
        score=score.score,
        priority=score.priority,
        extraction_success=False,
        last_error=extracted.get("last_error"),
        run_id=run_id,
    )

    upsert_lead(connection, lead)


def _extract_from_fetch(seed: SeedRow, fetch) -> dict:
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
        result = extract_lead_from_fetch(fetch)
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


def _export_csv_for_run(connection, *, run_id: int, min_score: int) -> Path:
    exports_dir = Path("exports")
    exports_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = exports_dir / f"leads_{ts}.csv"

    rows = connection.execute(
        """
        SELECT
          business_name, phone, email, website_url,
          platform, complexity, load_speed,
          city, state, category,
          score, priority,
          extraction_success, last_error
        FROM leads
        WHERE run_id = ? AND (score IS NOT NULL AND score >= ?)
        ORDER BY score DESC, extracted_at DESC
        """,
        (run_id, int(min_score)),
    ).fetchall()

    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=EXPORT_COLUMNS)
        writer.writeheader()
        for row in rows:
            record = dict(row)
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
            writer.writerow({k: record.get(k) for k in EXPORT_COLUMNS})

    return out_path


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
