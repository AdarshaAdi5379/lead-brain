from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from typing import Any, Optional


@dataclass(frozen=True)
class TechnologyDetection:
    lead_id: int
    technology_name: str
    category: str
    confidence: int
    evidence: tuple[str, ...] = ()


INSERT_SQL = """
INSERT INTO technology_detections (lead_id, technology_name, category, confidence, evidence)
VALUES (:lead_id, :technology_name, :category, :confidence, :evidence)
"""


def replace_detections(connection: sqlite3.Connection, lead_id: int, detections: list[Any]) -> None:
    """Delete any existing detections for a lead, then insert fresh ones.

    Keeps the table deterministic on re-runs (delete-by-lead-id + insert).
    """
    connection.execute("DELETE FROM technology_detections WHERE lead_id = ?", (int(lead_id),))
    for detection in detections:
        connection.execute(
            INSERT_SQL,
            {
                "lead_id": int(lead_id),
                "technology_name": str(detection.name),
                "category": str(detection.category),
                "confidence": int(detection.confidence),
                "evidence": json.dumps(list(detection.evidence)),
            },
        )
    connection.commit()


def detections_for_run(connection: sqlite3.Connection, run_id: int) -> list[dict[str, Any]]:
    """Fetch rows grouped by lead for a given pipeline run."""
    rows = connection.execute(
        """
        SELECT td.lead_id, td.technology_name, td.category, td.confidence, td.evidence
        FROM technology_detections td
        JOIN leads l ON l.id = td.lead_id
        WHERE l.run_id = ?
        ORDER BY td.confidence DESC, td.technology_name
        """,
        (int(run_id),),
    ).fetchall()
    result = []
    for row in rows:
        record = dict(row)
        try:
            record["evidence"] = json.loads(record["evidence"] or "[]")
        except (ValueError, TypeError):
            record["evidence"] = []
        result.append(record)
    return result


def detections_by_lead(connection: sqlite3.Connection) -> dict[int, list[dict[str, Any]]]:
    """Map lead_id -> sorted detections (used by the dashboard)."""
    rows = connection.execute(
        """
        SELECT lead_id, technology_name, category, confidence, evidence
        FROM technology_detections
        ORDER BY confidence DESC, technology_name
        """
    ).fetchall()
    grouped: dict[int, list[dict[str, Any]]] = {}
    for row in rows:
        record = dict(row)
        try:
            record["evidence"] = json.loads(record["evidence"] or "[]")
        except (ValueError, TypeError):
            record["evidence"] = []
        grouped.setdefault(record["lead_id"], []).append(record)
    return grouped


def get_lead_id_by_url(connection: sqlite3.Connection, website_url_normalized: str) -> Optional[int]:
    row = connection.execute(
        "SELECT id FROM leads WHERE website_url_normalized = ? LIMIT 1",
        (website_url_normalized,),
    ).fetchone()
    return int(row["id"]) if row is not None else None