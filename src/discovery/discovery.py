from __future__ import annotations

import csv
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from src.discovery.base import BusinessCandidate, get_provider
from src.discovery.models import DiscoveryQuery
from src.storage.normalization import normalize_url_for_dedupe
from src.url_loader import SeedRow

logger = logging.getLogger("lead.discovery")


def available_providers() -> list[str]:
    from src.discovery.base import available_providers as _available

    return _available()


@dataclass(frozen=True)
class DiscoveredLead:
    """Backward-compatible view of a discovered business (seed + metadata)."""

    seed: SeedRow
    place_id: str
    phone: Optional[str]
    rating: Optional[float]
    user_ratings_total: Optional[int]
    has_website: bool


def _candidate_rating(candidate: BusinessCandidate) -> Optional[float]:
    rating = candidate.raw.get("rating")
    if rating is None:
        return None
    try:
        return float(rating)
    except (TypeError, ValueError):
        return None


def _candidate_ratings_total(candidate: BusinessCandidate) -> Optional[int]:
    value = candidate.raw.get("user_ratings_total")
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _seed_key(seed: SeedRow) -> str:
    """Deterministic dedupe key: normalized URL, else business identity."""
    if seed.url:
        return normalize_url_for_dedupe(seed.url) or ""
    name = (seed.business_name or "").strip().lower()
    city = (seed.city or "").strip().lower()
    state = (seed.state or "").strip().lower()
    identity = "|".join([name, city, state]).strip("|")
    if identity:
        return f"biz:{identity}"
    if seed.osm_id:
        return f"osm:{seed.osm_id}"
    return ""


def _candidate_key(candidate: BusinessCandidate) -> str:
    if candidate.url:
        url = normalize_url_for_dedupe(candidate.url).rstrip("/")
        return url or ""
    name = (candidate.business_name or "").strip().lower()
    city = (candidate.city or "").strip().lower()
    identity = "|".join([name, city]).strip("|")
    if identity:
        return f"biz:{identity}"
    if candidate.osm_id:
        return f"osm:{candidate.osm_id}"
    return ""


def discover_candidates(
    queries: list[DiscoveryQuery],
    *,
    provider: str = "osm",
    radius: Optional[int] = None,
    limit: Optional[int] = None,
    min_rating: Optional[float] = None,
) -> list[BusinessCandidate]:
    """Run discovery through a named provider and return unique candidates.

    Failed queries are logged and skipped (no crash on a bad single location).
    ``min_rating`` filters only when the provider exposes ratings, and batch
    de-duplication uses normalized URL, else business identity.
    """
    provider_instance = get_provider(provider)

    results: list[BusinessCandidate] = []
    seen: set[str] = set()
    candidates = 0
    filtered = 0
    deduped = 0

    for query in queries:
        logger.info("Discovery query: category=%r location=%r (provider=%s)",
                    query.category, query.location, provider)
        try:
            found = provider_instance.search(query, radius=radius, limit=limit)
        except Exception as exc:
            logger.warning(
                "Discovery skipped for category=%r location=%r: %s",
                query.category,
                query.location,
                exc,
            )
            continue

        for candidate in found:
            candidates += 1
            rating = _candidate_rating(candidate)
            if min_rating is not None and rating is not None and rating < min_rating:
                filtered += 1
                continue

            key = _candidate_key(candidate)
            if key and key in seen:
                deduped += 1
                continue
            if key:
                seen.add(key)

            results.append(candidate)

    logger.info(
        "Discovery done (provider=%s): candidates=%d filtered=%d deduped=%d passed=%d",
        provider,
        candidates,
        filtered,
        deduped,
        len(results),
    )
    return results


def candidate_to_seed(candidate: BusinessCandidate, query: DiscoveryQuery) -> SeedRow:
    """Convert a provider candidate into the pipeline's seed schema."""
    city, state = _split_location(query.location)
    return SeedRow(
        business_name=candidate.business_name,
        category=candidate.category or query.category,
        url=candidate.url,
        city=candidate.city or city,
        state=candidate.state or state,
        phone=candidate.phone,
        email=candidate.email,
        country=candidate.country,
        osm_id=candidate.osm_id,
        osm_type=candidate.osm_type,
        latitude=candidate.latitude,
        longitude=candidate.longitude,
        address=candidate.address,
        postal_code=candidate.postal_code,
        opening_hours=candidate.opening_hours,
        source=candidate.source,
    )


def discover_to_seeds(
    queries: list[DiscoveryQuery],
    *,
    provider: str = "osm",
    radius: Optional[int] = None,
    limit: Optional[int] = None,
    min_rating: Optional[float] = None,
) -> list[SeedRow]:
    """Discover candidates and convert them directly into pipeline seed rows."""
    candidates = discover_candidates(
        queries, provider=provider, radius=radius, limit=limit, min_rating=min_rating
    )
    # Build a per-category query lookup so candidate conversion is deterministic.
    query_by_category: dict[str, DiscoveryQuery] = {}
    for query in queries:
        query_by_category.setdefault(query.category, query)

    seeds: list[SeedRow] = []
    for candidate in candidates:
        query = query_by_category.get(candidate.category) or DiscoveryQuery(
            category=candidate.category, location=""
        )
        seeds.append(candidate_to_seed(candidate, query))
    return seeds


def discover_leads(
    queries: list[DiscoveryQuery],
    *,
    provider: str = "osm",
    radius: Optional[int] = None,
    limit: Optional[int] = None,
    min_rating: Optional[float] = None,
) -> list[DiscoveredLead]:
    """Backward-compatible rich view of discovered businesses."""
    candidates = discover_candidates(
        queries, provider=provider, radius=radius, limit=limit, min_rating=min_rating
    )
    query_by_category: dict[str, DiscoveryQuery] = {}
    for query in queries:
        query_by_category.setdefault(query.category, query)

    leads: list[DiscoveredLead] = []
    for candidate in candidates:
        query = query_by_category.get(candidate.category) or DiscoveryQuery(
            category=candidate.category, location=""
        )
        leads.append(
            DiscoveredLead(
                seed=candidate_to_seed(candidate, query),
                place_id=candidate.osm_id or "",
                phone=candidate.phone,
                rating=_candidate_rating(candidate),
                user_ratings_total=_candidate_ratings_total(candidate),
                has_website=bool(candidate.url),
            )
        )
    return leads


def export_discovery_csv(candidates: list[BusinessCandidate], path: Path) -> None:
    """Write a traceability CSV with the full discovered candidate fields."""
    fieldnames = [
        "business_name",
        "category",
        "url",
        "phone",
        "email",
        "city",
        "state",
        "country",
        "latitude",
        "longitude",
        "address",
        "opening_hours",
        "osm_id",
        "osm_type",
        "source",
    ]
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for candidate in candidates:
            writer.writerow(
                {
                    "business_name": candidate.business_name,
                    "category": candidate.category,
                    "url": candidate.url or "",
                    "phone": candidate.phone or "",
                    "email": candidate.email or "",
                    "city": candidate.city or "",
                    "state": candidate.state or "",
                    "country": candidate.country or "",
                    "latitude": candidate.latitude,
                    "longitude": candidate.longitude,
                    "address": candidate.address or "",
                    "opening_hours": candidate.opening_hours or "",
                    "osm_id": candidate.osm_id or "",
                    "osm_type": candidate.osm_type or "",
                    "source": candidate.source,
                }
            )


def load_discovery_queries_csv(csv_path: Path) -> list[DiscoveryQuery]:
    if not csv_path.exists():
        raise FileNotFoundError(str(csv_path))

    queries: list[DiscoveryQuery] = []
    with csv_path.open("r", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise ValueError("CSV has no header row")

        for raw_row in reader:
            row = {k.strip().lower(): (v or "").strip() for k, v in raw_row.items() if k}
            category = row.get("category") or row.get("niche") or row.get("service") or ""
            location = row.get("location") or row.get("city") or ""
            if category and location:
                queries.append(DiscoveryQuery(category=category, location=location))

    if not queries:
        raise ValueError("No valid discovery queries found in CSV")

    return queries


def _split_location(location: str) -> tuple[str, str]:
    parts = [p.strip() for p in location.split(",")]
    if len(parts) >= 2:
        return parts[0], parts[-1]
    return location, ""