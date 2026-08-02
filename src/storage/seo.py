from __future__ import annotations

import json
import sqlite3
from typing import Any, Optional

SITE_FIELDS = [
    "site_score",
    "overall_health",
    "total_pages_audited",
    "html_pages",
    "pages_with_title",
    "pages_with_meta_description",
    "pages_with_h1",
    "pages_with_multiple_h1",
    "pages_with_noindex",
    "pages_with_canonical",
    "pages_with_json_ld",
    "pages_with_images_missing_alt",
    "pages_with_duplicate_titles",
    "pages_with_duplicate_descriptions",
    "pages_with_thin_content",
    "robots_txt_detected",
    "sitemap_detected",
]

PAGE_FIELDS = [
    "url",
    "page_type",
    "html_available",
    "title_present",
    "title_length",
    "meta_description_present",
    "meta_description_length",
    "h1_count",
    "h2_count",
    "canonical_present",
    "robots_meta",
    "viewport_present",
    "noindex",
    "nofollow",
    "word_count",
    "image_count",
    "images_missing_alt_count",
    "json_ld_present",
    "schema_present",
    "og_title_present",
    "og_description_present",
    "twitter_card_present",
    "internal_link_count",
    "score",
    "health",
]


def replace_audit(
    connection: sqlite3.Connection,
    lead_id: int,
    site: dict[str, Any],
    pages: list[dict[str, Any]],
) -> int:
    """Deterministically store one audit per lead (delete-then-insert).

    Re-running the pipeline for the same lead replaces the previous audit and
    its page rows, keeping results consistent on re-runs.
    """
    lead_id = int(lead_id)
    connection.execute("DELETE FROM seo_audits WHERE lead_id = ?", (lead_id,))

    site_values = {field: site.get(field, 0) for field in SITE_FIELDS}
    for field in ("robots_txt_detected", "sitemap_detected"):
        site_values[field] = int(bool(site_values[field]))
    for field in (
        "pages_with_title",
        "pages_with_meta_description",
        "pages_with_h1",
        "pages_with_multiple_h1",
        "pages_with_noindex",
        "pages_with_canonical",
        "pages_with_json_ld",
        "pages_with_images_missing_alt",
        "pages_with_duplicate_titles",
        "pages_with_duplicate_descriptions",
        "pages_with_thin_content",
        "total_pages_audited",
        "html_pages",
    ):
        site_values[field] = int(site_values.get(field) or 0)

    severity_summary = site.get("severity_summary", [])
    raw_summary = {key: value for key, value in site.items() if key != "severity_summary"}

    cursor = connection.execute(
        """
        INSERT INTO seo_audits (
          lead_id, site_score, overall_health,
          total_pages_audited, html_pages,
          pages_with_title, pages_with_meta_description,
          pages_with_h1, pages_with_multiple_h1,
          pages_with_noindex, pages_with_canonical, pages_with_json_ld,
          pages_with_images_missing_alt,
          pages_with_duplicate_titles, pages_with_duplicate_descriptions,
          pages_with_thin_content,
          robots_txt_detected, sitemap_detected,
          severity_summary, raw_summary_json
        ) VALUES (
          :lead_id, :site_score, :overall_health,
          :total_pages_audited, :html_pages,
          :pages_with_title, :pages_with_meta_description,
          :pages_with_h1, :pages_with_multiple_h1,
          :pages_with_noindex, :pages_with_canonical, :pages_with_json_ld,
          :pages_with_images_missing_alt,
          :pages_with_duplicate_titles, :pages_with_duplicate_descriptions,
          :pages_with_thin_content,
          :robots_txt_detected, :sitemap_detected,
          :severity_summary, :raw_summary_json
        )
        """,
        {
            **site_values,
            "lead_id": lead_id,
            "site_score": int(site.get("site_score") or 0),
            "overall_health": str(site.get("overall_health") or "Critical"),
            "severity_summary": json.dumps(severity_summary, ensure_ascii=False),
            "raw_summary_json": json.dumps(raw_summary, ensure_ascii=False),
        },
    )
    audit_id = int(cursor.lastrowid)

    for page in pages:
        page_values = {field: page.get(field, 0) for field in PAGE_FIELDS}
        for field in (
            "html_available",
            "title_present",
            "meta_description_present",
            "canonical_present",
            "robots_meta",
            "viewport_present",
            "noindex",
            "nofollow",
            "json_ld_present",
            "schema_present",
            "og_title_present",
            "og_description_present",
            "twitter_card_present",
        ):
            page_values[field] = int(bool(page_values.get(field)))
        issues_json = page.get("issues_json", "[]")
        if not isinstance(issues_json, str):
            issues_json = json.dumps(issues_json, ensure_ascii=False)
        connection.execute(
            """
            INSERT INTO seo_page_audits (
              seo_audit_id,
              url, page_type, html_available,
              title_present, title_length,
              meta_description_present, meta_description_length,
              h1_count, h2_count,
              canonical_present, robots_meta, viewport_present,
              noindex, nofollow,
              word_count, image_count, images_missing_alt_count,
              json_ld_present, schema_present,
              og_title_present, og_description_present, twitter_card_present,
              internal_link_count, score, health, issues_json
            ) VALUES (
              :seo_audit_id,
              :url, :page_type, :html_available,
              :title_present, :title_length,
              :meta_description_present, :meta_description_length,
              :h1_count, :h2_count,
              :canonical_present, :robots_meta, :viewport_present,
              :noindex, :nofollow,
              :word_count, :image_count, :images_missing_alt_count,
              :json_ld_present, :schema_present,
              :og_title_present, :og_description_present, :twitter_card_present,
              :internal_link_count, :score, :health, :issues_json
            )
            """,
            {
                **page_values,
                "seo_audit_id": audit_id,
                "url": str(page.get("url") or ""),
                "page_type": page.get("page_type"),
                "score": int(page.get("score") or 0),
                "health": str(page.get("health") or "Critical"),
                "issues_json": issues_json,
            },
        )

    connection.commit()
    return audit_id


def audits_for_run(connection: sqlite3.Connection, run_id: int) -> list[dict[str, Any]]:
    """Site-level audit rows for every lead in a pipeline run."""
    rows = connection.execute(
        """
        SELECT sa.*
        FROM seo_audits sa
        JOIN leads l ON l.id = sa.lead_id
        WHERE l.run_id = ?
        ORDER BY sa.site_score DESC
        """,
        (int(run_id),),
    ).fetchall()
    return [_decode_audit_row(row) for row in rows]


def audits_by_lead(connection: sqlite3.Connection) -> dict[int, dict[str, Any]]:
    """Latest site-level audit per lead (used by the dashboard)."""
    rows = connection.execute(
        "SELECT * FROM seo_audits ORDER BY id ASC"
    ).fetchall()
    return {int(row["lead_id"]): _decode_audit_row(row) for row in rows}


def page_audits_for_audit(connection: sqlite3.Connection, audit_id: int) -> list[dict[str, Any]]:
    rows = connection.execute(
        "SELECT * FROM seo_page_audits WHERE seo_audit_id = ? ORDER BY score ASC, url",
        (int(audit_id),),
    ).fetchall()
    audits: list[dict[str, Any]] = []
    for row in rows:
        record = dict(row)
        record["issues"] = _decode_json(record.get("issues_json"), [])
        audits.append(record)
    return audits


def _decode_audit_row(row: sqlite3.Row) -> dict[str, Any]:
    record = dict(row)
    record["severity_summary"] = _decode_json(record.get("severity_summary"), [])
    record["raw_summary_json"] = _decode_json(record.get("raw_summary_json"), {})
    return record


def _decode_json(value: Any, fallback: Any) -> Any:
    if value is None:
        return fallback
    try:
        return json.loads(value)
    except (ValueError, TypeError):
        return fallback
