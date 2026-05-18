from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional


@dataclass(frozen=True)
class SeedRow:
    business_name: str
    category: str
    url: Optional[str]
    city: str
    state: str


_COLUMN_ALIASES: dict[str, tuple[str, ...]] = {
    "business_name": ("business_name", "name", "business", "company", "company_name"),
    "category": ("category", "niche", "type", "service", "industry"),
    "url": ("url", "website", "website_url", "site", "link", "homepage"),
    "city": ("city", "town", "locality"),
    "state": ("state", "province", "region"),
}


def _first_present(row: dict[str, str], keys: Iterable[str]) -> str:
    for key in keys:
        if key in row:
            return row[key]
    return ""


def _clean_str(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _clean_url(value: str) -> Optional[str]:
    url = _clean_str(value)
    if not url:
        return None
    if "://" not in url:
        url = f"https://{url}"
    return url


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
            url = _clean_url(_first_present(row, _COLUMN_ALIASES["url"]))

            seeds.append(
                SeedRow(
                    business_name=business_name,
                    category=category,
                    url=url,
                    city=city,
                    state=state,
                )
            )

    return seeds


def _validate_required_columns(fieldnames: set[str]) -> None:
    missing: list[str] = []
    for required, aliases in _COLUMN_ALIASES.items():
        if not any(alias in fieldnames for alias in aliases):
            missing.append(required)

    if missing:
        details = ", ".join(
            f"{key} (aliases: {', '.join(_COLUMN_ALIASES[key])})" for key in missing
        )
        raise ValueError(f"CSV missing required columns: {details}")
