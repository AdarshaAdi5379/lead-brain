from __future__ import annotations

import json
import sqlite3
from typing import Any

from src.opportunities.base import OpportunityReport

OPPORTUNITY_COLUMNS = [
    "category",
    "label",
    "score",
    "severity",
    "confidence",
    "priority",
    "business_impact",
    "implementation_effort",
]


def replace_opportunities(
    connection: sqlite3.Connection,
    lead_id: int,
    report: OpportunityReport,
) -> int:
    """Deterministically store one row per detected opportunity.

    Re-running the pipeline for the same lead replaces all previous rows,
    keeping results consistent on re-runs.
    """
    lead_id = int(lead_id)
    connection.execute("DELETE FROM business_opportunities WHERE lead_id = ?", (lead_id,))

    inserted = 0
    for item in report.opportunities:
        values: dict[str, Any] = {"lead_id": lead_id}
        for field in OPPORTUNITY_COLUMNS:
            values[field] = getattr(item, field, "")
        values["recommended_services_json"] = json.dumps(
            list(item.recommended_services), ensure_ascii=False
        )
        values["evidence_json"] = json.dumps(list(item.evidence), ensure_ascii=False)
        values["priority"] = report.opportunity_priority

        connection.execute(
            """
            INSERT INTO business_opportunities (
              lead_id, category, label, score, severity,
              confidence, priority, business_impact, implementation_effort,
              recommended_services_json, evidence_json
            ) VALUES (
              :lead_id, :category, :label, :score, :severity,
              :confidence, :priority, :business_impact, :implementation_effort,
              :recommended_services_json, :evidence_json
            )
            """,
            values,
        )
        inserted += 1

    connection.commit()
    return inserted


def opportunities_for_run(
    connection: sqlite3.Connection, run_id: int
) -> list[dict[str, Any]]:
    """Opportunity rows for every lead in a pipeline run."""
    rows = connection.execute(
        """
        SELECT bo.*
        FROM business_opportunities bo
        JOIN leads l ON l.id = bo.lead_id
        WHERE l.run_id = ?
        ORDER BY bo.score DESC, bo.confidence DESC, bo.category
        """,
        (int(run_id),),
    ).fetchall()
    return [_decode_opportunity_row(row) for row in rows]


def opportunities_by_lead(
    connection: sqlite3.Connection,
) -> dict[int, list[dict[str, Any]]]:
    """Latest opportunity rows grouped per lead (used by the dashboard)."""
    rows = connection.execute(
        """
        SELECT * FROM business_opportunities
        ORDER BY lead_id ASC, score DESC, confidence DESC, category
        """
    ).fetchall()
    grouped: dict[int, list[dict[str, Any]]] = {}
    for row in rows:
        lead_id = int(row["lead_id"])
        grouped.setdefault(lead_id, []).append(_decode_opportunity_row(row))
    return grouped


def _decode_opportunity_row(row: sqlite3.Row) -> dict[str, Any]:
    record = dict(row)
    record["recommended_services"] = _decode_json(record.get("recommended_services_json"), [])
    record["evidence"] = _decode_json(record.get("evidence_json"), [])
    return record


def _decode_json(value: Any, fallback: Any) -> Any:
    if value is None:
        return fallback
    try:
        return json.loads(value)
    except (ValueError, TypeError):
        return fallback
