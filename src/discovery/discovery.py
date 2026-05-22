from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from src.discovery.places import PlaceCandidate, place_details, text_search
from src.storage.normalization import normalize_url_for_dedupe
from src.url_loader import SeedRow


@dataclass(frozen=True)
class DiscoveryQuery:
    category: str
    location: str


@dataclass(frozen=True)
class DiscoveredLead:
    seed: SeedRow
    place_id: str
    phone: Optional[str]
    rating: Optional[float]
    user_ratings_total: Optional[int]
    has_website: bool


def discover_leads(
    queries: list[DiscoveryQuery],
    *,
    radius: int = 50000,
    fetch_details: bool = True,
) -> list[DiscoveredLead]:
    results: list[DiscoveredLead] = []

    for query in queries:
        candidates = text_search(query.category, query.location, radius=radius)
        for candidate in candidates:
            enriched = candidate

            if fetch_details and not candidate.website:
                try:
                    enriched = place_details(candidate.place_id)
                except Exception:
                    enriched = candidate

            website = enriched.website
            url = _clean_website_url(website)
            has_website = bool(url)

            city, state = _split_location(query.location)

            seed = SeedRow(
                business_name=enriched.name or "",
                category=query.category,
                url=url,
                city=city,
                state=state,
            )

            results.append(
                DiscoveredLead(
                    seed=seed,
                    place_id=enriched.place_id,
                    phone=enriched.phone,
                    rating=enriched.rating,
                    user_ratings_total=enriched.user_ratings_total,
                    has_website=has_website,
                )
            )

    return results


def discover_to_seeds(
    queries: list[DiscoveryQuery],
    *,
    radius: int = 50000,
    fetch_details: bool = True,
    min_rating: Optional[float] = None,
) -> list[SeedRow]:
    leads = discover_leads(queries, radius=radius, fetch_details=fetch_details)
    seeds: list[SeedRow] = []
    seen_urls: set[str] = set()

    for lead in leads:
        if min_rating is not None:
            if lead.rating is not None and lead.rating < min_rating:
                continue

        seed = lead.seed
        dedupe_key = normalize_url_for_dedupe(seed.url) if seed.url else seed.business_name.lower()
        if dedupe_key and dedupe_key in seen_urls:
            continue
        if dedupe_key:
            seen_urls.add(dedupe_key)

        seeds.append(seed)

    return seeds


def export_discovery_csv(
    leads: list[DiscoveredLead],
    path: Path,
) -> None:
    fieldnames = [
        "business_name",
        "category",
        "url",
        "city",
        "state",
        "place_id",
        "phone",
        "rating",
        "user_ratings_total",
        "has_website",
    ]
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for lead in leads:
            writer.writerow(
                {
                    "business_name": lead.seed.business_name,
                    "category": lead.seed.category,
                    "url": lead.seed.url or "",
                    "city": lead.seed.city,
                    "state": lead.seed.state,
                    "place_id": lead.place_id,
                    "phone": lead.phone or "",
                    "rating": lead.rating,
                    "user_ratings_total": lead.user_ratings_total,
                    "has_website": "yes" if lead.has_website else "no",
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


def _clean_website_url(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    url = url.strip()
    if not url:
        return None
    if "://" not in url:
        url = f"https://{url}"
    return url


def _split_location(location: str) -> tuple[str, str]:
    parts = [p.strip() for p in location.split(",")]
    if len(parts) >= 2:
        return parts[0], parts[-1]
    return location, ""
