from __future__ import annotations

import logging
import math
from typing import Any, Optional

from src.discovery._http import HttpBackoff, cache_key
from src.discovery.base import BusinessCandidate, DiscoveryProvider, ProviderError
from src.discovery.cache import DiskCache
from src.discovery.models import DiscoveryQuery
from src.discovery.nominatim import geocode
from src.settings import (
    DISCOVERY_CACHE_DIR,
    DISCOVERY_POI_CACHE_TTL_HOURS,
    OVERPASS_API_URL,
    OVERPASS_DELAY_SECONDS,
    OVERPASS_MAX_RETRIES,
    OVERPASS_RADIUS,
    OVERPASS_RETRY_BACKOFF_SECONDS,
)
from src.storage.normalization import normalize_url_for_dedupe

logger = logging.getLogger("lead.discovery.osm")

# User-friendly category -> OSM tag filters. Important: OSM is tag-based, not
# free-text, so we keep a pragmatic mapping for common niches and fall back
# to a name-keyword search for anything unmapped.
CATEGORY_TAGS: dict[str, list[tuple[str, str]]] = {
    "plumber": [("craft", "plumber")],
    "electrician": [("craft", "electrician")],
    "hvac": [("craft", "hvac")],
    "roofer": [("craft", "roofer")],
    "painter": [("craft", "painter"), ("shop", "paint")],
    "landscaper": [("craft", "landscaper"), ("craft", "gardener")],
    "landscaping": [("craft", "landscaper"), ("craft", "gardener")],
    "handyman": [("craft", "handyman")],
    "locksmith": [("craft", "locksmith"), ("shop", "locksmith")],
    "tree service": [("craft", "tree_care")],
    "tree_service": [("craft", "tree_care")],
    "restaurant": [("amenity", "restaurant")],
    "cafe": [("amenity", "cafe")],
    "bakery": [("shop", "bakery")],
    "pizza": [("amenity", "restaurant"), ("cuisine", "pizza")],
    "salon": [("shop", "hairdresser")],
    "barber": [("shop", "barber")],
    "beauty": [("shop", "beauty")],
    "gym": [("leisure", "fitness_centre")],
    "fitness": [("leisure", "fitness_centre")],
    "car wash": [("amenity", "car_wash")],
    "car_wash": [("amenity", "car_wash")],
    "car repair": [("shop", "car_repair")],
    "car_repair": [("shop", "car_repair")],
    "auto repair": [("shop", "car_repair")],
    "dry cleaner": [("shop", "dry_cleaning")],
    "dry_cleaning": [("shop", "dry_cleaning")],
    "laundry": [("shop", "laundry")],
    "dentist": [("amenity", "dentist")],
    "pharmacy": [("amenity", "pharmacy")],
    "contractor": [("craft", "builder")],
    "general contractor": [("craft", "builder")],
    "flooring": [("craft", "floorer")],
    "window cleaning": [("craft", "window_cleaner")],
    "window_cleaner": [("craft", "window_cleaner")],
}


def normalize_category(category: str) -> str:
    """Lowercase/trim a user-supplied category for robust lookups."""
    return (category or "").strip().lower()


def overpass_tag_filters(category: str) -> list[tuple[str, str]]:
    """Return OSM ``[(key, value), ...]`` tag filters for a category.

    When there is no dedicated tag mapping we fall back to an exact-name
    search so unknown categories still return something.
    """
    category = normalize_category(category)
    if category in CATEGORY_TAGS:
        return list(CATEGORY_TAGS[category])
    return [("name", category)]


def _build_overpass_query(
    *,
    category: str,
    south: float,
    west: float,
    north: float,
    east: float,
    cap: int,
) -> str:
    filters = overpass_tag_filters(category)
    bbox = f"{south},{west},{north},{east}"
    clauses: list[str] = []
    tagged = [f for f in filters if f[0] != "name"]

    if tagged:
        for key, value in tagged:
            clauses.append(f'nwr["{key}"="{value}"]({bbox});')
    else:
        for key, value in filters:
            clauses.append(f'nwr["{key}"~"{value}",i]({bbox});')

    union = "(" + "".join(clauses) + ");"
    cap = max(1, int(cap))
    return f"[out:json][timeout:45];{union}out center tags {cap};"


def _bbox_around(lat: float, lon: float, radius_m: float) -> tuple[float, float, float, float]:
    """Approximate (s, w, n, e) box of ``radius_m`` around a point in metres."""
    d_lat = radius_m / 111_320.0
    d_lon = radius_m / (111_320.0 * max(0.01, abs(math.cos(math.radians(lat)))))
    return (lat - d_lat, lon - d_lon, lat + d_lat, lon + d_lon)


def _elem_coords(element: dict[str, Any]) -> Optional[tuple[float, float]]:
    center = element.get("center")
    if isinstance(center, dict):
        try:
            return float(center["lat"]), float(center["lon"])
        except (KeyError, TypeError, ValueError):
            return None
    try:
        return float(element["lat"]), float(element["lon"])
    except (KeyError, TypeError, ValueError):
        return None


def _first_tag(tags: dict[str, str], *keys: str) -> Optional[str]:
    for key in keys:
        value = tags.get(key)
        if value:
            return value
    return None


def _build_address(tags: dict[str, str]) -> Optional[str]:
    house = tags.get("addr:housenumber") or ""
    street = tags.get("addr:street") or ""
    place = " ".join(part for part in (house, street) if part).strip()
    parts = [
        part for part in (place, tags.get("addr:city"), tags.get("addr:postcode")) if part
    ]
    return ", ".join(parts) if parts else None


def _canonical_url(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    url = url.strip()
    if not url:
        return None
    normalized = normalize_url_for_dedupe(url)
    return normalized or None


def _element_to_candidate(element: dict[str, Any], category: str) -> Optional[BusinessCandidate]:
    tags = element.get("tags") or {}
    name = _first_tag(tags, "name", "name:en")
    if not name:
        return None

    coords = _elem_coords(element)
    lat, lon = (coords[0], coords[1]) if coords else (None, None)

    return BusinessCandidate(
        business_name=name,
        category=category,
        url=_canonical_url(_first_tag(tags, "website", "contact:website", "contact:web", "url")),
        phone=_first_tag(tags, "phone", "contact:phone", "tel"),
        email=_first_tag(tags, "email", "contact:email"),
        city=_first_tag(tags, "addr:city"),
        state=_first_tag(tags, "addr:state", "addr:province"),
        country=_first_tag(tags, "addr:country"),
        latitude=lat,
        longitude=lon,
        address=_build_address(tags),
        postal_code=_first_tag(tags, "addr:postcode"),
        opening_hours=_first_tag(tags, "opening_hours"),
        osm_id=str(element.get("id", "")),
        osm_type=str(element.get("type", "")),
        source="openstreetmap",
        raw=dict(tags),
    )


class OpenStreetMapProvider(DiscoveryProvider):
    """Discover businesses via the Overpass API (OpenStreetMap).

    Converts a category + location query into an OverpassQL search, honoring
    the free public endpoints' rate limits with a shared backoff and caching
    results locally so repeat runs are instant and offline-safe.
    """

    name = "osm"

    def __init__(self) -> None:
        self._http = HttpBackoff(
            delay=OVERPASS_DELAY_SECONDS,
            max_retries=OVERPASS_MAX_RETRIES,
            backoff=OVERPASS_RETRY_BACKOFF_SECONDS,
        )
        self._cache = DiskCache(DISCOVERY_CACHE_DIR, ttl_hours=DISCOVERY_POI_CACHE_TTL_HOURS)

    def search(
        self,
        query: DiscoveryQuery,
        *,
        radius: Optional[int] = None,
        limit: Optional[int] = None,
    ) -> list[BusinessCandidate]:
        category = normalize_category(query.category)
        location = (query.location or "").strip()
        if not location:
            raise ProviderError("Empty location for discovery query.")
        if not category:
            raise ProviderError("Empty category for discovery query.")

        point = geocode(location)
        if point is None:
            raise ProviderError(
                f"Could not geocode location '{query.location}'. "
                "Try a more specific place, e.g. 'Austin, TX'."
            )

        radius_m = int(radius or OVERPASS_RADIUS)
        cap = max(1, int(limit if limit is not None else 100))

        if point.bbox is not None:
            south, west, north, east = point.bbox
        else:
            south, west, north, east = _bbox_around(point.lat, point.lon, radius_m)

        ql = _build_overpass_query(
            category=category,
            south=south,
            west=west,
            north=north,
            east=east,
            cap=cap,
        )

        cache_key_value = cache_key("poi", category, location, south, west, north, east, cap)
        elements = self._cache.get(cache_key_value)
        if elements is None:
            logger.info("Overpass query: category=%r location=%r", category, location)
            try:
                data = self._http.post_form(OVERPASS_API_URL, {"data": ql})
            except Exception as exc:
                raise ProviderError(
                    f"Overpass request failed. Check your network or set "
                    f"OVERPASS_API_URL in .env. Detail: {exc}"
                ) from exc
            elements = data.get("elements", []) if isinstance(data, dict) else []
            self._cache.set(cache_key_value, elements)

        candidates = []
        for element in elements:
            candidate = _element_to_candidate(element, category)
            if candidate is not None:
                candidates.append(candidate)
        return candidates[:cap]


def smoke_run(category: str, location: str, limit: int = 10) -> None:
    """CLI smoke test helper: prints discovered candidates for a query."""
    provider = OpenStreetMapProvider()
    candidates = provider.search(
        DiscoveryQuery(category=category, location=location), limit=limit
    )
    print(f"Found {len(candidates)} candidate(s) for {category!r} in {location!r}:\n")
    if not candidates:
        print("  (none)")
    for i, c in enumerate(candidates, 1):
        print(f"{i:2d}. {c.business_name}")
        print(f"     url  : {c.url or '-'}")
        print(f"     phone: {c.phone or '-'}  email: {c.email or '-'}")
        print(f"     city : {c.city or '-'}  state: {c.state or '-'}  coords: "
              f"{c.latitude}, {c.longitude}")


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        print("Usage: python -m src.discovery.osm <category> <location> [limit]")
        sys.exit(2)
    smoke_run(sys.argv[1], sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 10)