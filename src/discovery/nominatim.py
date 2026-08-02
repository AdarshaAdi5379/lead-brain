from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from src.discovery._http import HttpBackoff, cache_key
from src.discovery.base import ProviderError
from src.discovery.cache import DiskCache
from src.settings import (
    DISCOVERY_CACHE_DIR,
    DISCOVERY_GEO_CACHE_TTL_HOURS,
    NOMINATIM_DELAY_SECONDS,
    NOMINATIM_MAX_RETRIES,
    NOMINATIM_REVERSE_URL,
    NOMINATIM_URL,
)


@dataclass(frozen=True)
class GeocodeResult:
    lat: float
    lon: float
    bbox: Optional[tuple[float, float, float, float]]  # (south, west, north, east)
    display_name: str
    country: Optional[str]
    place_id: str
    raw: dict[str, Any]


_harness = HttpBackoff(
    delay=NOMINATIM_DELAY_SECONDS,
    max_retries=NOMINATIM_MAX_RETRIES,
    backoff=2.0,
)
_cache = DiskCache(DISCOVERY_CACHE_DIR, ttl_hours=DISCOVERY_GEO_CACHE_TTL_HOURS)


def _parse_entry(entry: dict[str, Any]) -> Optional[GeocodeResult]:
    try:
        lat = float(entry["lat"])
        lon = float(entry["lon"])
    except (KeyError, TypeError, ValueError):
        return None

    bbox = None
    raw_bbox = entry.get("boundingbox") or []
    if len(raw_bbox) == 4:
        try:
            bbox = (float(raw_bbox[0]), float(raw_bbox[2]), float(raw_bbox[1]), float(raw_bbox[3]))
        except (TypeError, ValueError):
            bbox = None

    display_name = str(entry.get("display_name") or "")
    parts = [p.strip() for p in display_name.split(",") if p.strip()]
    country = parts[-1] if parts else None

    return GeocodeResult(
        lat=lat,
        lon=lon,
        bbox=bbox,
        display_name=display_name,
        country=country,
        place_id=str(entry.get("place_id") or entry.get("osm_id") or ""),
        raw=entry,
    )


def _request_json(url: str, params: dict[str, Any]) -> list[dict[str, Any]]:
    try:
        response = _harness.get_json(url, params)
    except Exception as exc:
        raise ProviderError(
            "Could not reach the location service (Nominatim). "
            "Check your network, or set NOMINATIM_URL in .env. Detail: "
            f"{exc}"
        ) from exc
    if not isinstance(response, list):
        raise ProviderError(
            f"Unexpected response from Nominatim: {type(response).__name__}"
        )
    return response


def _from_response(results: list[dict[str, Any]]) -> Optional[GeocodeResult]:
    return _parse_entry(results[0]) if results else None


def _serialize(result: GeocodeResult) -> dict[str, Any]:
    return {
        "lat": result.lat,
        "lon": result.lon,
        "bbox": list(result.bbox) if result.bbox else None,
        "display_name": result.display_name,
        "country": result.country,
        "place_id": result.place_id,
        "raw": result.raw,
    }


def geocode(location: str) -> Optional[GeocodeResult]:
    """Resolve a location (e.g. 'Austin, TX') to coordinates + optional bbox.

    Returns ``None`` when nothing matches. Raises ``ProviderError`` when the
    service is unreachable or broken. Responses are cached on disk for
    ``DISCOVERY_GEO_CACHE_TTL_HOURS`` (default 24h).
    """
    location = (location or "").strip()
    if not location:
        raise ProviderError("Empty location. Provide something like 'Austin, TX'.")

    key = cache_key("geocode", location)
    cached = _cache.get(key)
    if cached is not None:
        return _parse_entry(cached)

    results = _request_json(NOMINATIM_URL, {"format": "jsonv2", "q": location, "limit": 1})
    result = _from_response(results)
    if result is not None:
        _cache.set(key, _serialize(result))
    return result


def reverse_geocode(lat: float, lon: float) -> Optional[GeocodeResult]:
    """Reverse-geocode a point (useful to fill missing country/region)."""
    key = cache_key("reverse", float(lat), float(lon))
    cached = _cache.get(key)
    if cached is not None:
        return _parse_entry(cached)

    results = _request_json(
        NOMINATIM_REVERSE_URL,
        {"format": "jsonv2", "lat": str(lat), "lon": str(lon), "zoom": 10},
    )
    result = _from_response(results)
    if result is not None:
        _cache.set(key, _serialize(result))
    return result