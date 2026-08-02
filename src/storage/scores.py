from __future__ import annotations

import json
import sqlite3
from typing import Any, Optional

from src.scoring.base import LeadScore

SCORE_COLUMNS = [
    "final_score",
    "priority_label",
    "discovery_quality_score",
    "contactability_score",
    "technical_health_score",
    "seo_health_score",
    "content_strength_score",
    "trust_professionalism_score",
    "outreach_potential_score",
    "visual_presentation_score",
]

DIMENSION_TO_COLUMN = {
    "discovery_quality": "discovery_quality_score",
    "contactability": "contactability_score",
    "technical_health": "technical_health_score",
    "seo_health": "seo_health_score",
    "content_strength": "content_strength_score",
    "trust_professionalism": "trust_professionalism_score",
    "outreach_potential": "outreach_potential_score",
    "visual_presentation": "visual_presentation_score",
}


def replace_score(connection: sqlite3.Connection, lead_id: int, score: LeadScore) -> int:
    """Deterministically store one score row per lead (delete-then-insert).

    Re-running the pipeline for the same lead replaces the previous score,
    keeping results consistent on re-runs.
    """
    lead_id = int(lead_id)
    connection.execute("DELETE FROM lead_scores WHERE lead_id = ?", (lead_id,))

    values: dict[str, Any] = {"lead_id": lead_id}
    for field in SCORE_COLUMNS:
        values[field] = getattr(score, field, 0)
    for dimension, column in DIMENSION_TO_COLUMN.items():
        values[column] = int(score.dimension_scores.get(dimension) or 0)
    values["dimension_reasons_json"] = json.dumps(score.dimension_reasons, ensure_ascii=False)
    values["top_positive_reasons_json"] = json.dumps(score.top_positive_reasons, ensure_ascii=False)
    values["top_negative_reasons_json"] = json.dumps(score.top_negative_reasons, ensure_ascii=False)
    values["recommended_outreach_angle"] = score.recommended_outreach_angle

    cursor = connection.execute(
        """
        INSERT INTO lead_scores (
          lead_id,
          final_score, priority_label,
          discovery_quality_score, contactability_score,
          technical_health_score, seo_health_score,
          content_strength_score, trust_professionalism_score,
          outreach_potential_score, visual_presentation_score,
          dimension_reasons_json,
          top_positive_reasons_json,
          top_negative_reasons_json,
          recommended_outreach_angle
        ) VALUES (
          :lead_id,
          :final_score, :priority_label,
          :discovery_quality_score, :contactability_score,
          :technical_health_score, :seo_health_score,
          :content_strength_score, :trust_professionalism_score,
          :outreach_potential_score, :visual_presentation_score,
          :dimension_reasons_json,
          :top_positive_reasons_json,
          :top_negative_reasons_json,
          :recommended_outreach_angle
        )
        """,
        values,
    )
    connection.commit()
    return int(cursor.lastrowid)


def scores_for_run(connection: sqlite3.Connection, run_id: int) -> list[dict[str, Any]]:
    """Score rows for every lead in a pipeline run."""
    rows = connection.execute(
        """
        SELECT ls.*
        FROM lead_scores ls
        JOIN leads l ON l.id = ls.lead_id
        WHERE l.run_id = ?
        ORDER BY ls.final_score DESC
        """,
        (int(run_id),),
    ).fetchall()
    return [_decode_score_row(row) for row in rows]


def scores_by_lead(connection: sqlite3.Connection) -> dict[int, dict[str, Any]]:
    """Latest score row per lead (used by the dashboard)."""
    rows = connection.execute(
        "SELECT * FROM lead_scores ORDER BY id ASC"
    ).fetchall()
    return {int(row["lead_id"]): _decode_score_row(row) for row in rows}


def score_for_lead(connection: sqlite3.Connection, lead_id: int) -> Optional[dict[str, Any]]:
    row = connection.execute(
        "SELECT * FROM lead_scores WHERE lead_id = ?", (int(lead_id),)
    ).fetchone()
    if row is None:
        return None
    return _decode_score_row(row)


def _decode_score_row(row: sqlite3.Row) -> dict[str, Any]:
    record = dict(row)
    record["dimension_reasons"] = _decode_json(record.get("dimension_reasons_json"), {})
    record["top_positive_reasons"] = _decode_json(record.get("top_positive_reasons_json"), [])
    record["top_negative_reasons"] = _decode_json(record.get("top_negative_reasons_json"), [])
    return record


def _decode_json(value: Any, fallback: Any) -> Any:
    if value is None:
        return fallback
    try:
        return json.loads(value)
    except (ValueError, TypeError):
        return fallback
