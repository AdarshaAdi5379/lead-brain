"""Enrichment lookup cache: SQLite-backed TTL + in-memory overlay."""

from __future__ import annotations

import time
import unittest

from src.enrichment.base import LeadContext
from src.enrichment.cache import CacheEntry, EnrichmentCache, query_key

from tests.enrichment_fixtures import EnrichmentSqliteFixture, lead


def _ctx(**overrides) -> LeadContext:
    return LeadContext(**lead(**overrides))


class TestQueryKey(unittest.TestCase):
    def test_stable_and_discriminative(self) -> None:
        k1 = query_key(_ctx())
        k2 = query_key(_ctx())
        k3 = query_key(_ctx(business_name="Other Plumbing"))
        self.assertEqual(k1, k2)
        self.assertNotEqual(k1, k3)


class TestEnrichmentCache(EnrichmentSqliteFixture):
    def test_set_and_get_roundtrip(self) -> None:
        cache = EnrichmentCache(self.connection, ttl_days=30)
        key = query_key(_ctx())
        cache.set(key, CacheEntry(status="found", website_url="https://x.com", source="web_search", confidence=0.9))
        entry = cache.get(key)
        self.assertEqual(entry.status, "found")
        self.assertEqual(entry.website_url, "https://x.com")
        self.assertEqual(entry.source, "web_search")

    def test_expired_entry_misses(self) -> None:
        cache = EnrichmentCache(self.connection, ttl_days=1)
        key = query_key(_ctx())
        stale = CacheEntry(status="not_found", checked_at=time.time() - 2 * 86_400)
        cache.set(key, stale)
        self.assertIsNone(cache.get(key))

    def test_zero_ttl_never_expires(self) -> None:
        cache = EnrichmentCache(self.connection, ttl_days=0)
        key = query_key(_ctx())
        stale = CacheEntry(status="not_found", checked_at=time.time() - 365 * 86_400)
        cache.set(key, stale)
        self.assertIsNotNone(cache.get(key))

    def test_unknown_key_misses(self) -> None:
        cache = EnrichmentCache(self.connection, ttl_days=30)
        self.assertIsNone(cache.get(query_key(_ctx())))

    def test_same_run_overlay_prevents_repeated_lookups(self) -> None:
        cache = EnrichmentCache(self.connection, ttl_days=30)
        key = query_key(_ctx())
        cache.set(key, CacheEntry(status="not_found"))
        # A fresh cache instance over the same DB still sees the row.
        cache2 = EnrichmentCache(self.connection, ttl_days=30)
        self.assertIsNotNone(cache2.get(key))


if __name__ == "__main__":
    unittest.main()