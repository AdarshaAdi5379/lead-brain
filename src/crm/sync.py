from __future__ import annotations

import sqlite3
from typing import Any, Mapping, Optional, Sequence

from src.crm.columns import COLUMNS, DEFAULT_STATUS, MANUAL_COLUMNS
from src.crm.workbook import normalise_row
from src.outreach.context import build_outreach_context
from src.storage.leads import update_crm_fields
from src.storage.search import leads_intelligence

# Two-way sync between the SQLite technical store and the Excel CRM workbook.
#
#  * build_sqlite_rows  — auto-filled rows derived from existing project data;
#  * merge_rows         — manual workbook columns win over regenerated values;
#  * sync_manual_to_sqlite — writes the editable CRM fields back to SQLite.


def build_sqlite_rows(connection: sqlite3.Connection) -> list[dict[str, Any]]:
    """One CRM row per lead, auto-filled from SQLite (blanks for missing data)."""
    intelligence = leads_intelligence(connection)
    rows: list[dict[str, Any]] = []
    for lead_id in sorted(intelligence):
        intel = intelligence[lead_id]
        lead = intel.get("lead") or {}
        score = intel.get("score") or {}
        seo = intel.get("seo") or {}
        visual = intel.get("visual") or {}
        opportunities = intel.get("opportunities") or []
        outreach_context = build_outreach_context(intel) or {}
        reachability = outreach_context.get("reachability") or {}

        row: dict[str, Any] = {column: None for column in COLUMNS}
        row["lead_id"] = int(lead_id)
        for key in (
            "business_name", "category", "city", "state", "country",
            "website_url", "phone", "email", "address", "opening_hours",
            "facebook_url", "instagram_url", "linkedin_url", "twitter_url",
            "youtube_url", "whatsapp_url", "contact_page_url",
            "contact_form_url", "google_maps_url", "platform", "notes",
        ):
            row[key] = lead.get(key)
        lead_score = score.get("final_score")
        if lead_score is None:
            lead_score = lead.get("score")
        row["lead_score"] = lead_score
        row["seo_score"] = seo.get("site_score")
        row["visual_score"] = visual.get("visual_score")
        row["opportunity_score"] = (
            max(int(o.get("score") or 0) for o in opportunities) if opportunities else None
        )
        row["priority_label"] = score.get("priority_label") or lead.get("priority")
        row["recommended_outreach_angle"] = score.get("recommended_outreach_angle")
        row["best_contact_method"] = reachability.get("best_contact_method")
        row["status"] = DEFAULT_STATUS
        rows.append(row)
    return rows


def merge_rows(
    auto_rows: Sequence[Mapping[str, Any]],
    manual_rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Merged CRsM rows: manually edited fields win over regenerated defaults.

    Auto rows are the backbone (one per SQLite lead, ordered by lead_id).
    Manual values only override when present and non-empty, so an empty manual
    status still falls back to the default instead of going blank.
    """
    manual_by_id: dict[int, dict[str, Any]] = {}
    for row in manual_rows:
        try:
            lead_id = int(row.get("lead_id"))
        except (TypeError, ValueError):
            continue
        manual_by_id[lead_id] = dict(row)

    merged: list[dict[str, Any]] = []
    for auto in auto_rows:
        try:
            lead_id = int(auto.get("lead_id"))
        except (TypeError, ValueError):
            continue
        row = dict(auto)
        manual = manual_by_id.get(lead_id)
        if manual is not None:
            for column in MANUAL_COLUMNS:
                value = manual.get(column)
                if value is None:
                    continue
                cleaned = normalise_value(column, value)
                if column in ("last_contacted", "next_follow_up") and cleaned is None:
                    continue
                if cleaned not in (None, ""):
                    row[column] = cleaned
        merged.append(row)
    return merged


def normalise_value(column: str, value: Any) -> Any:
    """Consistent cell cleaning for one merge value (blank-safe)."""
    cleaned = normalise_row({column: value}).get(column)
    return cleaned


def sync_manual_to_sqlite(
    connection: sqlite3.Connection, rows: Sequence[Mapping[str, Any]]
) -> int:
    """Write editable CRM fields back to SQLite; returns the number written."""
    written = 0
    for row in rows:
        try:
            lead_id = int(row.get("lead_id"))
        except (TypeError, ValueError):
            continue
        values: dict[str, Any] = {}
        for column in MANUAL_COLUMNS:
            cleaned = normalise_value(column, row.get(column))
            if cleaned not in (None, ""):
                values[column] = cleaned
        if not values:
            continue
        affected = update_crm_fields(connection, lead_id, **values)
        if affected > 0:
            written += 1
    return written


def has_manual_edits(manual_rows: Sequence[Mapping[str, Any]]) -> bool:
    """True when any workbook row carries a non-default manual field."""
    for row in manual_rows:
        for column in MANUAL_COLUMNS:
            value = row.get(column)
            if value is not None and str(value).strip():
                return True
    return False