from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

from src.net.url_guard import UnsafeUrlError, validate_public_http_url

# A leading token urllib would interpret as a scheme (letters/digits/+/-/. but
# must start with a letter) followed by ':'.
_SCHEME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.\-]*:")


@dataclass(frozen=True)
class SeedRow:
    business_name: str
    category: str
    url: Optional[str]
    city: str
    state: str
    # Enriched fields discovered via a provider (e.g. OpenStreetMap). Optional
    # so the manual CSV loader remains fully backward compatible.
    phone: Optional[str] = None
    email: Optional[str] = None
    country: Optional[str] = None
    osm_id: Optional[str] = None
    osm_type: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    address: Optional[str] = None
    postal_code: Optional[str] = None
    opening_hours: Optional[str] = None
    source: Optional[str] = None
    # Website enrichment (set by the pre-pipeline enrichment pass).
    enrichment_status: Optional[str] = None
    enrichment_source: Optional[str] = None
    enrichment_confidence: Optional[float] = None
    enrichment_last_error: Optional[str] = None
    enrichment_last_checked_at: Optional[str] = None
    # Set when a non-empty seed URL was rejected by the URL trust boundary
    # (src/net/url_guard.py). The URL is kept out of every fetch path, but the
    # reason is preserved so runs report "Invalid/unsafe website URL" instead
    # of silently classifying the row as "no website".
    url_error: Optional[str] = None


_COLUMN_ALIASES: dict[str, tuple[str, ...]] = {
    "business_name": ("business_name", "name", "business", "company", "company_name"),
    "category": ("category", "niche", "type", "service", "industry"),
    "url": ("url", "website", "website_url", "site", "link", "homepage"),
    "city": ("city", "town", "locality"),
    "state": ("state", "province", "region"),
    "phone": ("phone", "telephone", "contact_phone"),
    "email": ("email", "e_mail", "contact_email"),
    "country": ("country", "nation"),
    "osm_id": ("osm_id", "osm"),
    "osm_type": ("osm_type",),
    "latitude": ("latitude", "lat"),
    "longitude": ("longitude", "lon", "lng"),
    "address": ("address", "addr"),
    "postal_code": ("postal_code", "postcode", "zip", "zip_code"),
    "opening_hours": ("opening_hours", "hours"),
    "source": ("source", "origin"),
}

# Only these base columns must exist in a seed CSV; everything else in
# _COLUMN_ALIASES is optional (providers add them).
_REQUIRED_COLUMNS = ("business_name", "category", "url", "city", "state")


def _first_present(row: dict[str, str], keys: Iterable[str]) -> str:
    for key in keys:
        if key in row:
            return row[key]
    return ""


def _clean_str(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _validated_seed_url(
    value: str,
) -> tuple[Optional[str], Optional[str]]:
    """Return ``(url, url_error)`` for a raw CSV cell.

    A valid public http(s) URL passes through unchanged. An unsafe URL is
    rejected *before it can reach Playwright* (SSRF boundary); the reason is
    returned so reporting can distinguish it from a missing URL.
    """
    raw = _clean_str(value)
    if not raw:
        return None, None
    # Only prepend the default scheme for bare domains: an explicit scheme is
    # anything urllib would treat as one ("data:", "javascript:", "ftp:"...) —
    # but ports on bare hosts ("example.com:8080") are NOT schemes.
    candidate = raw if _SCHEME_RE.match(raw) else f"https://{raw}"
    try:
        return validate_public_http_url(candidate, resolve_dns=False), None
    except UnsafeUrlError as exc:
        return None, f"Invalid/unsafe website URL ({exc})"


def load_seed_csv(csv_path: Path) -> list[SeedRow]:
    """
    Loads the manual seed list CSV.

    Requirements (v1):
    - Accept alternate column names for the required fields.
    - Keep rows with empty URL (url=None) so the pipeline can treat them as
      "no website" leads later.
    """

    if not csv_path.exists():
        raise FileNotFoundError(str(csv_path))

    seeds: list[SeedRow] = []
    with csv_path.open("r", newline="", encoding="utf-8-sig") as file:
        reader = csv.DictReader(file)
        if reader.fieldnames is None:
            raise ValueError("CSV has no header row")

        normalized_fieldnames = [field.strip().lower() for field in reader.fieldnames]
        reader.fieldnames = normalized_fieldnames
        _validate_required_columns(set(normalized_fieldnames))

        for raw_row in reader:
            row: dict[str, str] = {k.strip().lower(): (v or "") for k, v in raw_row.items() if k}

            business_name = _clean_str(_first_present(row, _COLUMN_ALIASES["business_name"]))
            category = _clean_str(_first_present(row, _COLUMN_ALIASES["category"]))
            city = _clean_str(_first_present(row, _COLUMN_ALIASES["city"]))
            state = _clean_str(_first_present(row, _COLUMN_ALIASES["state"]))
            url, url_error = _validated_seed_url(_first_present(row, _COLUMN_ALIASES["url"]))

            seeds.append(
                SeedRow(
                    business_name=business_name,
                    category=category,
                    url=url,
                    city=city,
                    state=state,
                    phone=_clean_optional(row, _COLUMN_ALIASES["phone"]),
                    email=_clean_optional(row, _COLUMN_ALIASES["email"]),
                    country=_clean_optional(row, _COLUMN_ALIASES["country"]),
                    osm_id=_clean_optional(row, _COLUMN_ALIASES["osm_id"]),
                    osm_type=_clean_optional(row, _COLUMN_ALIASES["osm_type"]),
                    latitude=_float_optional(row, _COLUMN_ALIASES["latitude"]),
                    longitude=_float_optional(row, _COLUMN_ALIASES["longitude"]),
                    address=_clean_optional(row, _COLUMN_ALIASES["address"]),
                    postal_code=_clean_optional(row, _COLUMN_ALIASES["postal_code"]),
                    opening_hours=_clean_optional(row, _COLUMN_ALIASES["opening_hours"]),
                    source=_clean_optional(row, _COLUMN_ALIASES["source"]),
                    url_error=url_error,
                )
            )

    return seeds


def _clean_optional(row: dict[str, str], keys: Iterable[str]) -> Optional[str]:
    value = _first_present(row, keys)
    return _clean_str(value) or None


def _as_float(value: object) -> Optional[float]:
    try:
        number = float(str(value).strip())
    except (TypeError, ValueError):
        return None
    return number


def _float_optional(row: dict[str, str], keys: Iterable[str]) -> Optional[float]:
    raw = _first_present(row, keys)
    return _as_float(raw) if raw else None


def _validate_required_columns(fieldnames: set[str]) -> None:
    missing: list[str] = []
    for required in _REQUIRED_COLUMNS:
        aliases = _COLUMN_ALIASES[required]
        if not any(alias in fieldnames for alias in aliases):
            missing.append(required)

    if missing:
        details = ", ".join(
            f"{key} (aliases: {', '.join(_COLUMN_ALIASES[key])})" for key in missing
        )
        raise ValueError(f"CSV missing required columns: {details}")
