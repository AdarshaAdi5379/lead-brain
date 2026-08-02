from __future__ import annotations

import json
import sqlite3
from typing import Any, Optional

SITE_FIELDS = [
    "visual_score",
    "visual_health_label",
    "summary",
    "total_pages_audited",
    "pages_with_desktop_screenshot",
    "pages_with_mobile_screenshot",
    "pages_with_modern_design_signal",
    "pages_with_clutter_signal",
    "pages_with_weak_hierarchy_signal",
    "pages_with_weak_mobile_signal",
    "pages_with_weak_cta_signal",
    "pages_with_strong_brand_signal",
]

PAGE_FIELDS = [
    "url",
    "page_type",
    "screenshot_available",
    "mobile_screenshot_available",
    "screenshot_path",
    "mobile_screenshot_path",
    "screenshot_hash",
    "visual_score",
    "layout_quality",
    "readability_quality",
    "branding_quality",
    "mobile_quality",
    "conversion_quality",
    "confidence",
]


def replace_visual_audit(
    connection: sqlite3.Connection,
    lead_id: int,
    site: dict[str, Any],
    pages: list[dict[str, Any]],
) -> int:
    """Deterministically store one visual audit per lead (delete-then-insert).

    Mirrors :func:`src.storage.seo.replace_audit`: re-runs replace the
    previous audit and its page rows, keeping results consistent.
    """
    lead_id = int(lead_id)
    connection.execute("DELETE FROM visual_audits WHERE lead_id = ?", (lead_id,))

    site_values = {field: site.get(field, 0) for field in SITE_FIELDS}
    for field in (
        "total_pages_audited",
        "pages_with_desktop_screenshot",
        "pages_with_mobile_screenshot",
        "pages_with_modern_design_signal",
        "pages_with_clutter_signal",
        "pages_with_weak_hierarchy_signal",
        "pages_with_weak_mobile_signal",
        "pages_with_weak_cta_signal",
        "pages_with_strong_brand_signal",
    ):
        site_values[field] = int(site_values.get(field) or 0)

    raw_summary = {key: value for key, value in site.items() if key != "pages"}

    cursor = connection.execute(
        """
        INSERT INTO visual_audits (
          lead_id, visual_score, visual_health_label, summary,
          total_pages_audited,
          pages_with_desktop_screenshot, pages_with_mobile_screenshot,
          pages_with_modern_design_signal, pages_with_clutter_signal,
          pages_with_weak_hierarchy_signal, pages_with_weak_mobile_signal,
          pages_with_weak_cta_signal, pages_with_strong_brand_signal,
          llm_summary, raw_summary_json
        ) VALUES (
          :lead_id, :visual_score, :visual_health_label, :summary,
          :total_pages_audited,
          :pages_with_desktop_screenshot, :pages_with_mobile_screenshot,
          :pages_with_modern_design_signal, :pages_with_clutter_signal,
          :pages_with_weak_hierarchy_signal, :pages_with_weak_mobile_signal,
          :pages_with_weak_cta_signal, :pages_with_strong_brand_signal,
          :llm_summary, :raw_summary_json
        )
        """,
        {
            **site_values,
            "lead_id": lead_id,
            "visual_score": int(site.get("visual_score") or 0),
            "visual_health_label": str(site.get("visual_health_label") or "Critical"),
            "summary": str(site.get("summary") or ""),
            "llm_summary": site.get("llm_summary"),
            "raw_summary_json": json.dumps(raw_summary, ensure_ascii=False),
        },
    )
    audit_id = int(cursor.lastrowid)

    for page in pages:
        page_values = {field: page.get(field) for field in PAGE_FIELDS}
        for field in ("screenshot_available", "mobile_screenshot_available"):
            page_values[field] = int(bool(page_values.get(field)))
        issues_json = page.get("issues_json", "[]")
        strengths_json = page.get("strengths_json", "[]")
        evidence_json = page.get("evidence_json", "{}")
        if not isinstance(issues_json, str):
            issues_json = json.dumps(issues_json, ensure_ascii=False)
        if not isinstance(strengths_json, str):
            strengths_json = json.dumps(strengths_json, ensure_ascii=False)
        if not isinstance(evidence_json, str):
            evidence_json = json.dumps(evidence_json, ensure_ascii=False)
        connection.execute(
            """
            INSERT INTO visual_page_audits (
              visual_audit_id,
              url, page_type,
              screenshot_available, mobile_screenshot_available,
              screenshot_path, mobile_screenshot_path, screenshot_hash,
              visual_score, layout_quality, readability_quality,
              branding_quality, mobile_quality, conversion_quality,
              confidence, issues_json, strengths_json, evidence_json
            ) VALUES (
              :visual_audit_id,
              :url, :page_type,
              :screenshot_available, :mobile_screenshot_available,
              :screenshot_path, :mobile_screenshot_path, :screenshot_hash,
              :visual_score, :layout_quality, :readability_quality,
              :branding_quality, :mobile_quality, :conversion_quality,
              :confidence, :issues_json, :strengths_json, :evidence_json
            )
            """,
            {
                **page_values,
                "visual_audit_id": audit_id,
                "url": str(page.get("url") or ""),
                "page_type": page.get("page_type"),
                "visual_score": int(page.get("visual_score") or 0),
                "layout_quality": int(page.get("layout_quality") or 0),
                "readability_quality": int(page.get("readability_quality") or 0),
                "branding_quality": int(page.get("branding_quality") or 0),
                "mobile_quality": int(page.get("mobile_quality") or 0),
                "conversion_quality": int(page.get("conversion_quality") or 0),
                "confidence": float(page.get("confidence") or 0.0),
                "issues_json": issues_json,
                "strengths_json": strengths_json,
                "evidence_json": evidence_json,
            },
        )

    connection.commit()
    return audit_id


def audits_for_run(connection: sqlite3.Connection, run_id: int) -> list[dict[str, Any]]:
    """Site-level visual audit rows for every lead in a pipeline run."""
    rows = connection.execute(
        """
        SELECT va.*
        FROM visual_audits va
        JOIN leads l ON l.id = va.lead_id
        WHERE l.run_id = ?
        ORDER BY va.visual_score DESC
        """,
        (int(run_id),),
    ).fetchall()
    return [_decode_audit_row(row) for row in rows]


def audits_by_lead(connection: sqlite3.Connection) -> dict[int, dict[str, Any]]:
    """Latest site-level visual audit per lead (used by the dashboard)."""
    rows = connection.execute("SELECT * FROM visual_audits ORDER BY id ASC").fetchall()
    return {int(row["lead_id"]): _decode_audit_row(row) for row in rows}


def page_audits_for_audit(
    connection: sqlite3.Connection, audit_id: int
) -> list[dict[str, Any]]:
    rows = connection.execute(
        "SELECT * FROM visual_page_audits WHERE visual_audit_id = ? ORDER BY visual_score ASC, url",
        (int(audit_id),),
    ).fetchall()
    audits: list[dict[str, Any]] = []
    for row in rows:
        record = dict(row)
        record["issues"] = _decode_json(record.get("issues_json"), [])
        record["strengths"] = _decode_json(record.get("strengths_json"), [])
        record["evidence"] = _decode_json(record.get("evidence_json"), {})
        audits.append(record)
    return audits


def _decode_audit_row(row: sqlite3.Row) -> dict[str, Any]:
    record = dict(row)
    record["raw_summary_json"] = _decode_json(record.get("raw_summary_json"), {})
    return record


def _decode_json(value: Any, fallback: Any) -> Any:
    if value is None:
        return fallback
    try:
        return json.loads(value)
    except (ValueError, TypeError):
        return fallback
