from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Optional

from src.settings import GOOGLE_MAPS_API_KEY, PLACES_LANGUAGE, PLACES_TEXT_SEARCH_RADIUS


@dataclass(frozen=True)
class PlaceCandidate:
    place_id: str
    name: str
    address: Optional[str]
    rating: Optional[float]
    user_ratings_total: Optional[int]
    phone: Optional[str]
    website: Optional[str]
    types: list[str]
    raw: dict[str, Any]


class GooglePlacesError(RuntimeError):
    def __init__(self, status: str, message: str) -> None:
        super().__init__(f"Google Places API error ({status}): {message}")
        self.status = status
        self.message = message


def text_search(category: str, location: str, *, radius: int = 50000) -> list[PlaceCandidate]:
    query = f"{category} in {location}"
    params = {
        "query": query,
        "key": _api_key(),
        "language": PLACES_LANGUAGE,
        "radius": str(max(1, radius)),
    }
    data = _get_json("/maps/api/place/textsearch/json", params)

    status = data.get("status", "")
    if status != "OK":
        if status == "ZERO_RESULTS":
            return []
        raise GooglePlacesError(status, data.get("error_message", ""))

    candidates = []
    for result in data.get("results", []):
        candidates.append(
            PlaceCandidate(
                place_id=result.get("place_id", ""),
                name=result.get("name", ""),
                address=result.get("formatted_address"),
                rating=_as_float_optional(result.get("rating")),
                user_ratings_total=_as_int_optional(result.get("user_ratings_total")),
                phone=result.get("formatted_phone_number"),
                website=result.get("website"),
                types=result.get("types", []),
                raw=_strip_result(result),
            )
        )
    return candidates


def place_details(place_id: str) -> PlaceCandidate:
    fields = [
        "place_id",
        "name",
        "formatted_address",
        "rating",
        "user_ratings_total",
        "formatted_phone_number",
        "website",
        "types",
    ]
    params = {
        "place_id": place_id,
        "key": _api_key(),
        "language": PLACES_LANGUAGE,
        "fields": ",".join(fields),
    }
    data = _get_json("/maps/api/place/details/json", params)

    status = data.get("status", "")
    if status != "OK":
        raise GooglePlacesError(status, data.get("error_message", ""))

    result = data.get("result", {})
    return PlaceCandidate(
        place_id=result.get("place_id", place_id),
        name=result.get("name", ""),
        address=result.get("formatted_address"),
        rating=_as_float_optional(result.get("rating")),
        user_ratings_total=_as_int_optional(result.get("user_ratings_total")),
        phone=result.get("formatted_phone_number"),
        website=result.get("website"),
        types=result.get("types", []),
        raw=_strip_result(result),
    )


def _get_json(path: str, params: dict[str, str]) -> dict[str, Any]:
    base = "https://maps.googleapis.com"
    url = f"{base}{path}?{urllib.parse.urlencode(params)}"

    try:
        with urllib.request.urlopen(url, timeout=30) as response:
            raw = response.read().decode("utf-8", errors="replace")
            return json.loads(raw)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace") if hasattr(exc, "read") else str(exc)
        raise GooglePlacesError(str(getattr(exc, "code", 0)), body[:2000]) from exc


def _api_key() -> str:
    if not GOOGLE_MAPS_API_KEY:
        raise RuntimeError(
            "GOOGLE_MAPS_API_KEY is not set. Add it to your .env file."
        )
    return GOOGLE_MAPS_API_KEY


def _as_float_optional(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except Exception:
        return None


def _as_int_optional(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except Exception:
        return None


def _strip_result(result: dict[str, Any]) -> dict[str, Any]:
    keep = {
        "place_id",
        "name",
        "formatted_address",
        "rating",
        "user_ratings_total",
        "formatted_phone_number",
        "website",
        "types",
        "business_status",
        "price_level",
        "vicinity",
    }
    return {k: v for k, v in result.items() if k in keep}
