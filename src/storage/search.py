from __future__ import annotations

import json
import sqlite3
from typing import Any, Optional

# Persistence primitives for the local semantic search index (lead_embeddings).
#
# The SQLite table is the canonical store: it keeps the document text, the
# content/embedding hashes, the flat filter metadata and a JSON copy of the
# embedding vector, so the dependency-free search path is fully self-contained.
# The optional ChromaDB store is only a mirror/accelerator on top of it.
#
# This module also gathers the per-lead "intelligence" (lead row + technology
# detections + SEO + visual + scoring + opportunities) used by the document
# builder and the AI context builder. It reads the same decoded row shapes the
# dashboard consumes.


def _decode_json(value: Any, fallback: Any) -> Any:
    if value is None:
        return fallback
    try:
        return json.loads(value)
    except (ValueError, TypeError):
        return fallback


def upsert_embedding(
    connection: sqlite3.Connection,
    *,
    lead_id: int,
    document_hash: str,
    embedding_hash: str,
    embedder_id: str,
    document_text: str,
    metadata: dict[str, Any],
    embedding: list[float],
) -> None:
    """Insert or replace one embedding row (delete-then-insert semantics).

    ``lead_embeddings.lead_id`` is the primary key, so re-indexing a lead
    overwrites its row instead of duplicating it.
    """
    connection.execute(
        """
        INSERT INTO lead_embeddings (
          lead_id, document_hash, embedding_hash, embedder_id,
          document_text, metadata_json, embedding_json, embedding_dim,
          updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
        ON CONFLICT(lead_id) DO UPDATE SET
          document_hash = excluded.document_hash,
          embedding_hash = excluded.embedding_hash,
          embedder_id = excluded.embedder_id,
          document_text = excluded.document_text,
          metadata_json = excluded.metadata_json,
          embedding_json = excluded.embedding_json,
          embedding_dim = excluded.embedding_dim,
          updated_at = datetime('now')
        """,
        (
            int(lead_id),
            document_hash,
            embedding_hash,
            embedder_id,
            document_text,
            json.dumps(metadata, ensure_ascii=False, separators=(",", ":")),
            json.dumps(embedding, separators=(",", ":")),
            len(embedding),
        ),
    )
    connection.commit()


def get_embedding_row(
    connection: sqlite3.Connection, lead_id: int
) -> Optional[dict[str, Any]]:
    """Decoded embedding row for one lead (None when not indexed)."""
    row = connection.execute(
        "SELECT * FROM lead_embeddings WHERE lead_id = ?", (int(lead_id),)
    ).fetchone()
    if row is None:
        return None
    return _decode_embedding_row(row)


def delete_embedding(connection: sqlite3.Connection, lead_id: int) -> bool:
    """Remove one lead from the index. Returns True when a row was deleted."""
    cursor = connection.execute(
        "DELETE FROM lead_embeddings WHERE lead_id = ?", (int(lead_id),)
    )
    connection.commit()
    return cursor.rowcount > 0


def clear_embeddings(connection: sqlite3.Connection) -> int:
    """Remove every embedding row (full rebuild path). Returns row count."""
    cursor = connection.execute("DELETE FROM lead_embeddings")
    connection.commit()
    return cursor.rowcount


def count_embeddings(connection: sqlite3.Connection) -> int:
    row = connection.execute("SELECT COUNT(*) AS n FROM lead_embeddings").fetchone()
    return int(row["n"])


def embeddings_for_run(
    connection: sqlite3.Connection, run_id: int
) -> list[dict[str, Any]]:
    """Decoded embedding rows for every lead processed in a pipeline run."""
    rows = connection.execute(
        """
        SELECT le.*
        FROM lead_embeddings le
        JOIN leads l ON l.id = le.lead_id
        WHERE l.run_id = ?
        ORDER BY le.lead_id
        """,
        (int(run_id),),
    ).fetchall()
    return [_decode_embedding_row(row) for row in rows]


def all_embedding_rows(connection: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = connection.execute("SELECT * FROM lead_embeddings ORDER BY lead_id").fetchall()
    return [_decode_embedding_row(row) for row in rows]


def _decode_embedding_row(row: sqlite3.Row) -> dict[str, Any]:
    record = dict(row)
    record["metadata"] = _decode_json(record.get("metadata_json"), {})
    record["embedding"] = _decode_json(record.get("embedding_json"), [])
    return record


# --- per-lead intelligence --------------------------------------------------


def lead_intelligence(
    connection: sqlite3.Connection, lead_id: int
) -> Optional[dict[str, Any]]:
    """All collected intelligence for one lead, or None when it does not exist."""
    lead = connection.execute(
        "SELECT * FROM leads WHERE id = ?", (int(lead_id),)
    ).fetchone()
    if lead is None:
        return None
    by_lead = leads_intelligence(connection, lead_ids=[int(lead_id)])
    return by_lead.get(int(lead_id))


def leads_intelligence(
    connection: sqlite3.Connection,
    run_id: Optional[int] = None,
    lead_ids: Optional[list[int]] = None,
) -> dict[int, dict[str, Any]]:
    """Bulk per-lead intelligence in a few table scans (fast at 10k+ leads).

    Returns ``{lead_id: {"lead": {...}, "detections": [...], "seo": {...}|None,
    "visual": {...}|None, "score": {...}|None, "opportunities": [...]}}``.
    """
    if lead_ids:
        placeholders = ",".join("?" * len(lead_ids))
        lead_rows = connection.execute(
            f"SELECT * FROM leads WHERE id IN ({placeholders}) ORDER BY id",
            [int(i) for i in lead_ids],
        ).fetchall()
    elif run_id is not None:
        lead_rows = connection.execute(
            "SELECT * FROM leads WHERE run_id = ? ORDER BY id", (int(run_id),)
        ).fetchall()
    else:
        lead_rows = connection.execute("SELECT * FROM leads ORDER BY id").fetchall()

    leads: list[dict[str, Any]] = [dict(row) for row in lead_rows]
    if not leads:
        return {}

    def _in_clause() -> str:
        return ",".join("?" * len(leads))

    detections: dict[int, list[dict[str, Any]]] = {}
    for row in connection.execute(
        f"SELECT * FROM technology_detections WHERE lead_id IN ({_in_clause()}) ORDER BY lead_id, confidence DESC",
        [int(lead["id"]) for lead in leads],
    ).fetchall():
        record = dict(row)
        record["evidence"] = _decode_json(record.get("evidence"), [])
        detections.setdefault(int(record["lead_id"]), []).append(record)

    def _by_lead(table: str) -> dict[int, dict[str, Any]]:
        mapping: dict[int, dict[str, Any]] = {}
        for row in connection.execute(
            f"SELECT * FROM {table} WHERE lead_id IN ({_in_clause()})",
            [int(lead["id"]) for lead in leads],
        ).fetchall():
            mapping[int(row["lead_id"])] = dict(row)
        return mapping

    seo_rows = _by_lead("seo_audits")
    visual_rows = _by_lead("visual_audits")
    score_rows = _by_lead("lead_scores")

    opportunities: dict[int, list[dict[str, Any]]] = {}
    for row in connection.execute(
        f"SELECT * FROM business_opportunities WHERE lead_id IN ({_in_clause()}) ORDER BY lead_id, score DESC",
        [int(lead["id"]) for lead in leads],
    ).fetchall():
        record = dict(row)
        record["evidence"] = _decode_json(record.get("evidence_json"), [])
        record["recommended_services"] = _decode_json(
            record.get("recommended_services_json"), []
        )
        opportunities.setdefault(int(record["lead_id"]), []).append(record)

    intelligence: dict[int, dict[str, Any]] = {}
    for lead in leads:
        lead_id = int(lead["id"])
        intelligence[lead_id] = {
            "lead": lead,
            "detections": detections.get(lead_id, []),
            "seo": _decode_audit_row(seo_rows.get(lead_id)) if lead_id in seo_rows else None,
            "visual": (
                _decode_visual_row(visual_rows.get(lead_id))
                if lead_id in visual_rows
                else None
            ),
            "score": (
                _decode_score_row(score_rows.get(lead_id)) if lead_id in score_rows else None
            ),
            "opportunities": opportunities.get(lead_id, []),
        }
    return intelligence


def _decode_audit_row(row: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
    if row is None:
        return None
    record = dict(row)
    record["severity_summary"] = _decode_json(record.get("severity_summary"), [])
    record["raw_summary_json"] = _decode_json(record.get("raw_summary_json"), {})
    return record


def _decode_visual_row(row: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
    if row is None:
        return None
    record = dict(row)
    record["raw_summary_json"] = _decode_json(record.get("raw_summary_json"), {})
    return record


def _decode_score_row(row: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
    if row is None:
        return None
    record = dict(row)
    record["dimension_reasons"] = _decode_json(record.get("dimension_reasons_json"), {})
    record["top_positive_reasons"] = _decode_json(
        record.get("top_positive_reasons_json"), []
    )
    record["top_negative_reasons"] = _decode_json(
        record.get("top_negative_reasons_json"), []
    )
    return record
