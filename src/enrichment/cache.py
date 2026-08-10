from __future__ import annotations

import hashlib
import sqlite3
import time
from dataclasses import dataclass
from typing import Optional

from src.enrichment.base import LeadContext


@dataclass(frozen=True)
class CacheEntry:
    status: str
    website_url: Optional[str] = None
    source: Optional[str] = None
    confidence: Optional[float] = None
    error: Optional[str] = None
    checked_at: float = 0.0


def query_key(lead: LeadContext) -> str:
    """Stable lookup key: one entry per business (name + location + category)."""
    parts = [
        lead.business_name or "",
        lead.city or "",
        lead.state or "",
        lead.category or "",
    ]
    payload = "|".join(str(part).strip().lower() for part in parts)
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


class EnrichmentCache:
    """Local SQLite-backed cache for enrichment lookups.

    Avoids re-searching the same business within the TTL window (and within
    the same run, via an in-memory overlay). Failed lookups are never cached:
    transient errors must be retried on the next run.
    """

    def __init__(self, connection: sqlite3.Connection, ttl_days: int = 30) -> None:
        self.connection = connection
        self.ttl_seconds = max(0, int(ttl_days)) * 86_400
        self._memory: dict[str, CacheEntry] = {}

    def get(self, key: str) -> Optional[CacheEntry]:
        if key in self._memory:
            entry = self._memory[key]
            if self.ttl_seconds <= 0 or time.time() - entry.checked_at <= self.ttl_seconds:
                return entry
        row = self.connection.execute(
            "SELECT status, website_url, source, confidence, error, checked_at "
            "FROM website_enrichment_cache WHERE query_key = ?",
            (key,),
        ).fetchone()
        if row is None:
            return None
        entry = CacheEntry(
            status=row[0],
            website_url=row[1],
            source=row[2],
            confidence=row[3],
            error=row[4],
            checked_at=float(row[5] or 0),
        )
        if self.ttl_seconds > 0 and time.time() - entry.checked_at > self.ttl_seconds:
            return None
        self._memory[key] = entry
        return entry

    def set(self, key: str, entry: CacheEntry) -> None:
        self.connection.execute(
            "INSERT OR REPLACE INTO website_enrichment_cache "
            "(query_key, status, website_url, source, confidence, error, checked_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                key,
                entry.status,
                entry.website_url,
                entry.source,
                entry.confidence,
                entry.error,
                entry.checked_at or time.time(),
            ),
        )
        self.connection.commit()
        self._memory[key] = entry