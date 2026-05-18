from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class RunStats:
    total_urls_processed: int
    successful_extractions: int
    failed_extractions: int
    total_cost_usd: float


def start_run(connection: sqlite3.Connection) -> int:
    started_at = _utc_now_iso()
    cursor = connection.execute(
        "INSERT INTO scraping_runs (started_at) VALUES (?)",
        (started_at,),
    )
    connection.commit()
    return int(cursor.lastrowid)


def update_run_stats(connection: sqlite3.Connection, run_id: int, stats: RunStats) -> None:
    connection.execute(
        """
        UPDATE scraping_runs
        SET
          total_urls_processed = ?,
          successful_extractions = ?,
          failed_extractions = ?,
          total_cost_usd = ?
        WHERE run_id = ?
        """,
        (
            stats.total_urls_processed,
            stats.successful_extractions,
            stats.failed_extractions,
            float(stats.total_cost_usd),
            run_id,
        ),
    )
    connection.commit()


def complete_run(connection: sqlite3.Connection, run_id: int) -> None:
    completed_at = _utc_now_iso()
    connection.execute(
        "UPDATE scraping_runs SET completed_at = ? WHERE run_id = ?",
        (completed_at, run_id),
    )
    connection.commit()


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()

