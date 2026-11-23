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
    OVERPASS_FALLBACK_URLS,
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
    "interiors": [
        ("office", "interior_design"),
        ("shop", "interior_decorator"),
        ("craft", "interior_decorator"),
    ],
    "interior": [
        ("office", "interior_design"),
        ("shop", "interior_decorator"),
        ("craft", "interior_decorator"),
    ],
    "interior design": [
        ("office", "interior_design"),
        ("shop", "interior_decorator"),
        ("craft", "interior_decorator"),
    ],
    "interior designer": [
        ("office", "interior_design"),
        ("shop", "interior_decorator"),
        ("craft", "interior_decorator"),
    ],
    "interior decorator": [
        ("office", "interior_design"),
        ("shop", "interior_decorator"),
        ("craft", "interior_decorator"),
    ],
    "furniture": [("shop", "furniture"), ("craft", "joiner")],
    "architect": [("office", "architect")],
    "architecture": [("office", "architect")],
    "lawyer": [("office", "lawyer")],
    "attorney": [("office", "lawyer")],
    "legal": [("office", "lawyer")],
    "accountant": [("office", "accountant"), ("office", "tax_advisor")],
    "accounting": [("office", "accountant"), ("office", "tax_advisor")],
    "tax": [("office", "tax_advisor")],
    "photographer": [("shop", "photo"), ("craft", "photographer")],
    "photography": [("shop", "photo"), ("craft", "photographer")],
    "catering": [("craft", "caterer"), ("amenity", "restaurant")],
    "caterer": [("craft", "caterer")],
    "veterinarian": [("amenity", "veterinary")],
    "vet": [("amenity", "veterinary")],
    "pet groomer": [("shop", "pet_grooming")],
    "pest control": [("craft", "pest_control")],
    "real estate": [("office", "estate_agent")],
    "realtor": [("office", "estate_agent")],
    "cleaning": [("craft", "cleaner"), ("shop", "cleaning")],
    "solar": [("shop", "solar"), ("craft", "electrician")],
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

    for key, value in filters:
        if key == "name":
            # For fallback name searches, restrict to commercial/POI entities so
            # Overpass doesn't scan millions of non-POI nodes/ways (which times out).
            clauses.append(
                f'nw["{key}"~"{value}",i][~"^(amenity|shop|office|craft|healthcare|tourism|leisure|commercial)$"~"."]({bbox});'
            )
        else:
            clauses.append(f'nw["{key}"="{value}"]({bbox});')

    union = "(" + "".join(clauses) + ");"
    cap = max(1, int(cap))
    return f"[out:json][timeout:20];{union}out center tags {cap};"


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
        sample_cap = min(max(cap * 3, 50), 200) if cap < 100 else cap

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
            cap=sample_cap,
        )

        cache_key_value = cache_key("poi", category, location, south, west, north, east, sample_cap)
        elements = self._cache.get(cache_key_value)
        if elements is None:
            logger.info("Overpass query: category=%r location=%r", category, location)
            endpoints = list(dict.fromkeys([OVERPASS_API_URL, *OVERPASS_FALLBACK_URLS]))
            data: Optional[dict[str, Any]] = None
            last_exc: Optional[BaseException] = None
            for endpoint in endpoints:
                try:
                    data = self._http.post_form(endpoint, {"data": ql})
                    break
                except Exception as exc:
                    last_exc = exc
                    logger.warning("Overpass endpoint %s failed: %s", endpoint, exc)
            if data is None:
                logger.info(
                    "Overpass endpoints unavailable (%s); falling back to Nominatim POI search for %r in %r",
                    last_exc,
                    category,
                    location,
                )
                candidates = self._search_nominatim(category, location, cap=sample_cap)
                if candidates:
                    return candidates[:cap]
                raise ProviderError(
                    f"Overpass request failed on all {len(endpoints)} endpoint(s) and Nominatim fallback had no results. "
                    f"Detail: {last_exc}"
                ) from last_exc
            elements = data.get("elements", []) if isinstance(data, dict) else []
            self._cache.set(cache_key_value, elements)

        candidates = []
        for element in elements:
            candidate = _element_to_candidate(element, category)
            if candidate is not None:
                candidates.append(candidate)

        # Fallback to Nominatim if Overpass returned zero candidates
        if not candidates:
            candidates = self._search_nominatim(category, location, cap=sample_cap)

        # Prioritize candidates: website present > phone/email present > address present
        def _candidate_rank(c: BusinessCandidate) -> tuple[int, int, int]:
            has_url = 1 if c.url else 0
            has_contact = 1 if (c.phone or c.email) else 0
            has_address = 1 if c.address else 0
            return (has_url, has_contact, has_address)

        # Filter out ghost map pins that have NO website AND NO phone AND NO email AND NO address.
        # A lead with zero contact channels and no website cannot be audited, called, emailed, or pitched.
        actionable_candidates = [
            c for c in candidates
            if bool(c.url or c.phone or c.email or c.address)
        ]
        pool = actionable_candidates if actionable_candidates else candidates
        pool.sort(key=_candidate_rank, reverse=True)
        return pool[:cap]

    def _search_nominatim(
        self, category: str, location: str, cap: int
    ) -> list[BusinessCandidate]:
        """Fallback POI search using Nominatim when Overpass is overloaded or returns empty."""
        import json
        import urllib.parse
        import urllib.request
        from src.settings import NOMINATIM_URL, OSM_USER_AGENT

        cache_key_val = cache_key("nominatim_poi", category, location, cap)
        cached = self._cache.get(cache_key_val)
        if cached is not None and isinstance(cached, list):
            items = cached
        else:
            q = f"{category} in {location}"
            params = {
                "q": q,
                "format": "jsonv2",
                "limit": min(max(cap * 2, 20), 50),
                "addressdetails": 1,
                "extratags": 1,
            }
            url = f"{NOMINATIM_URL}?{urllib.parse.urlencode(params)}"
            req = urllib.request.Request(
                url,
                headers={"User-Agent": OSM_USER_AGENT, "Accept": "application/json"},
            )
            try:
                with urllib.request.urlopen(req, timeout=12) as resp:
                    items = json.loads(resp.read().decode("utf-8"))
                if isinstance(items, list):
                    self._cache.set(cache_key_val, items)
                else:
                    items = []
            except Exception as exc:
                logger.warning("Nominatim POI search fallback failed: %s", exc)
                return []

        candidates: list[BusinessCandidate] = []
        for item in items:
            name = item.get("name")
            if not name:
                display = item.get("display_name", "")
                name = display.split(",")[0].strip() if display else ""
            if not name or len(name) < 2:
                continue

            extratags = item.get("extratags") or {}
            address = item.get("address") or {}

            url = _canonical_url(
                extratags.get("website")
                or extratags.get("contact:website")
                or extratags.get("contact:web")
                or extratags.get("url")
            )
            phone = (
                extratags.get("phone")
                or extratags.get("contact:phone")
                or extratags.get("tel")
            )
            email = extratags.get("email") or extratags.get("contact:email")
            city = (
                address.get("city")
                or address.get("town")
                or address.get("suburb")
                or address.get("city_district")
            )
            state = address.get("state")
            postcode = address.get("postcode")
            country = address.get("country")
            formatted_address = item.get("display_name")

            lat = float(item["lat"]) if "lat" in item else None
            lon = float(item["lon"]) if "lon" in item else None

            candidates.append(
                BusinessCandidate(
                    business_name=name,
                    category=category,
                    url=url,
                    phone=phone,
                    email=email,
                    city=city,
                    state=state,
                    postal_code=postcode,
                    country=country,
                    address=formatted_address,
                    latitude=lat,
                    longitude=lon,
                    osm_id=str(item.get("osm_id") or ""),
                    osm_type=str(item.get("osm_type") or ""),
                    source="openstreetmap",
                    raw=item,
                )
            )

        def _candidate_rank(c: BusinessCandidate) -> tuple[int, int, int]:
            has_url = 1 if c.url else 0
            has_contact = 1 if (c.phone or c.email) else 0
            has_address = 1 if c.address else 0
            return (has_url, has_contact, has_address)

        candidates.sort(key=_candidate_rank, reverse=True)
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