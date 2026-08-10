from __future__ import annotations

import sqlite3
from typing import Optional

from src.storage.normalization import normalize_url_for_dedupe

# Website enrichment persistence: ships a verified website into any row that
# already exists under the no-website dedupe key (`biz://...`), so re-runs
# keep one row per business. Fresh leads get their enrichment fields through
# the normal upsert; this module only touches already-stored rows.

_ENRICHMENT_SET_SQL = """
UPDATE leads SET
  enrichment_status = ?,
  enrichment_source = ?,
  enrichment_confidence = ?,
  enrichment_last_error = ?,
  enrichment_last_checked_at = ?
WHERE website_url_normalized = ?
"""


def _enrichment_params(
    *,
    status: str,
    source: Optional[str],
    confidence: Optional[float],
    last_error: Optional[str],
    checked_at: Optional[str],
) -> tuple:
    return (status, source, confidence, last_error, checked_at)


def _find_no_website_rows(
    connection: sqlite3.Connection,
    *,
    business_name: Optional[str],
    city: Optional[str],
    state: Optional[str],
    category: Optional[str],
) -> list[tuple[int, str]]:
    """Rows stored under a `biz://` dedupe key matching this business."""
    rows = connection.execute(
        """
        SELECT id, website_url_normalized FROM leads
        WHERE website_url_normalized LIKE 'biz://%'
          AND business_name = ?
          AND COALESCE(city, '') = COALESCE(?, '')
          AND COALESCE(state, '') = COALESCE(?, '')
          AND COALESCE(category, '') = COALESCE(?, '')
        """,
        (business_name, city, state, category),
    ).fetchall()
    return [(int(row[0]), str(row[1])) for row in rows]


def apply_enrichment_to_existing(
    connection: sqlite3.Connection,
    *,
    business_name: Optional[str],
    city: Optional[str],
    state: Optional[str],
    category: Optional[str],
    website_url: str,
    status: str,
    source: Optional[str],
    confidence: Optional[float],
    last_error: Optional[str],
    checked_at: Optional[str],
) -> None:
    """Migrate a stored no-website lead to its verified website key.

    - When a `biz://`-keyed row exists (and no row yet uses the verified URL
      key), the row is migrated in place: same lead id, real website URL, and
      enrichment fields stamped. The normal crawl upsert then updates it.
    - When the URL-keyed row already exists (an earlier enriched run), only
      the enrichment fields are refreshed.
    - When no row exists yet, nothing is written: the pipeline's own upsert
      creates the lead from the enriched seed.
    """
    normalized_website = normalize_url_for_dedupe(website_url)
    url_row = connection.execute(
        "SELECT 1 FROM leads WHERE website_url_normalized = ? LIMIT 1",
        (normalized_website,),
    ).fetchone()
    if url_row is not None:
        connection.execute(
            _ENRICHMENT_SET_SQL,
            (*_enrichment_params(
                status=status,
                source=source,
                confidence=confidence,
                last_error=last_error,
                checked_at=checked_at,
            ), normalized_website),
        )
        connection.commit()
        return

    biz_rows = _find_no_website_rows(
        connection,
        business_name=business_name,
        city=city,
        state=state,
        category=category,
    )
    if not biz_rows:
        return
    params = _enrichment_params(
        status=status,
        source=source,
        confidence=confidence,
        last_error=last_error,
        checked_at=checked_at,
    )
    for row_id, _old_key in biz_rows:
        connection.execute(
            "UPDATE leads SET website_url = ?, website_url_normalized = ?, "
            "enrichment_status = ?, enrichment_source = ?, "
            "enrichment_confidence = ?, enrichment_last_error = ?, "
            "enrichment_last_checked_at = ? WHERE id = ?",
            (website_url, normalized_website, *params, row_id),
        )
    connection.commit()