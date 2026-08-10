"""Website enrichment service: end-to-end flows with injected fakes.

Covers found / not_found / low_confidence / failed statuses, cache hits,
same-run dedupe, email-domain sourcing, and in-place migration of existing
no-website lead rows (no duplicates across re-runs).
"""

from __future__ import annotations

import unittest

from src.enrichment.config import EnrichmentConfig
from src.enrichment.service import run_enrichment
from src.storage.enrichment import apply_enrichment_to_existing
from src.storage.leads import LeadUpsert, upsert_lead

from tests.enrichment_fixtures import (
    EnrichmentSqliteFixture,
    failing_page,
    matching_page,
    seed,
)


class _CountingSearch:
    def __init__(self, urls=None) -> None:
        self.urls = urls or []
        self.calls = 0

    def __call__(self, query: str) -> list[str]:
        self.calls += 1
        return list(self.urls)


class TestRunEnrichmentFound(EnrichmentSqliteFixture):
    def setUp(self) -> None:
        super().setUp()
        self.config = EnrichmentConfig(search_enabled=True, max_candidates=3)

    def test_fresh_lead_gets_verified_website(self) -> None:
        search = _CountingSearch(["https://radiantplumbing.com/"])
        enriched, report = run_enrichment(
            self.connection,
            [seed()],
            self.config,
            search_client=search,
            fetcher=lambda url: matching_page(),
        )
        out = enriched[0]
        self.assertEqual(out.url, "https://radiantplumbing.com/")
        self.assertEqual(out.enrichment_status, "found")
        self.assertEqual(out.enrichment_source, "web_search")
        self.assertGreaterEqual(out.enrichment_confidence, 0.75)
        self.assertIsNotNone(out.enrichment_last_checked_at)
        self.assertEqual(report.found, 1)
        self.assertEqual(report.processed, 1)

    def test_existing_no_website_row_migrated_in_place(self) -> None:
        upsert_lead(
            self.connection,
            LeadUpsert(
                website_url=None,
                business_name="Radiant Plumbing",
                city="Austin",
                state="TX",
                category="plumber",
                source="openstreetmap",
            ),
        )
        before = self.connection.execute(
            "SELECT website_url_normalized FROM leads"
        ).fetchone()
        self.assertTrue(str(before[0]).startswith("biz://"))

        search = _CountingSearch(["https://radiantplumbing.com/"])
        run_enrichment(
            self.connection,
            [seed()],
            self.config,
            search_client=search,
            fetcher=lambda url: matching_page(),
        )

        rows = self.connection.execute(
            "SELECT website_url, website_url_normalized, enrichment_status, "
            "enrichment_source, enrichment_confidence FROM leads"
        ).fetchall()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["website_url"], "https://radiantplumbing.com/")
        self.assertFalse(rows[0]["website_url_normalized"].startswith("biz://"))
        self.assertEqual(rows[0]["enrichment_status"], "found")
        self.assertEqual(rows[0]["enrichment_source"], "web_search")

    def test_email_domain_source_when_search_disabled(self) -> None:
        config = EnrichmentConfig(search_enabled=False)
        enriched, report = run_enrichment(
            self.connection,
            [seed(email="hello@radiantplumbing.com")],
            config,
            search_client=_CountingSearch(),
            fetcher=lambda url: matching_page(),
        )
        out = enriched[0]
        self.assertEqual(out.url, "https://radiantplumbing.com")
        self.assertEqual(out.enrichment_source, "email_domain")
        self.assertEqual(report.found, 1)
        self.assertIn("email_domain", report.sources)

    def test_two_identical_seeds_search_twice_ok_and_dedupe(self) -> None:
        # Same business twice in one run: second lookup comes from the cache.
        search = _CountingSearch(["https://radiantplumbing.com/"])
        seeds = [seed(), seed()]
        enriched, report = run_enrichment(
            self.connection,
            seeds,
            self.config,
            search_client=search,
            fetcher=lambda url: matching_page(),
        )
        self.assertEqual(search.calls, 1)
        self.assertEqual(report.found, 2)
        self.assertEqual(enriched[0].url, enriched[1].url)


class TestRunEnrichmentNoMatch(EnrichmentSqliteFixture):
    def setUp(self) -> None:
        super().setUp()
        self.config = EnrichmentConfig(search_enabled=True)

    def test_no_candidates_keeps_lead_valid(self) -> None:
        search = _CountingSearch([])
        enriched, report = run_enrichment(
            self.connection,
            [seed()],
            self.config,
            search_client=search,
            fetcher=lambda url: failing_page(),
        )
        out = enriched[0]
        self.assertIsNone(out.url)
        self.assertEqual(out.enrichment_status, "not_found")
        self.assertTrue(report.not_found == 1)
        # The lead is still a valid website-less lead.
        self.assertEqual(out.business_name, "Radiant Plumbing")

    def test_low_confidence_rejected(self) -> None:
        # Candidate verifies but only a partial brand signal fires.
        from tests.enrichment_fixtures import html_page

        partial = html_page("Unrelated Title", "friends at Radiant called once")
        search = _CountingSearch(["https://someplumber.com/"])
        enriched, report = run_enrichment(
            self.connection,
            [seed()],
            self.config,
            search_client=search,
            fetcher=lambda url: partial,
        )
        out = enriched[0]
        self.assertIsNone(out.url)
        self.assertEqual(out.enrichment_status, "low_confidence")
        self.assertIn("scored", out.enrichment_last_error or "")
        self.assertTrue(report.low_confidence == 1)

    def test_all_fetches_failed_status(self) -> None:
        search = _CountingSearch(["https://radiantplumbing.com/", "https://other.com/"])
        enriched, report = run_enrichment(
            self.connection,
            [seed()],
            self.config,
            search_client=search,
            fetcher=lambda url: failing_page("timeout"),
        )
        out = enriched[0]
        self.assertIsNone(out.url)
        self.assertEqual(out.enrichment_status, "failed")
        self.assertIn("could be fetched", out.enrichment_last_error or "")
        self.assertTrue(report.failed == 1)

    def test_failures_not_cached_so_next_run_retries(self) -> None:
        search = _CountingSearch(["https://radiantplumbing.com/"])
        run_enrichment(
            self.connection,
            [seed()],
            self.config,
            search_client=search,
            fetcher=lambda url: failing_page("timeout"),
        )
        cached = self.connection.execute(
            "SELECT status FROM website_enrichment_cache"
        ).fetchall()
        self.assertEqual(cached, [])

    def test_osmos_tags_source_not_needed_when_url_present(self) -> None:
        enriched, report = run_enrichment(
            self.connection,
            [seed(url="https://already-known.com/")],
            self.config,
            search_client=_CountingSearch(),
            fetcher=lambda url: matching_page(),
        )
        self.assertEqual(enriched[0].url, "https://already-known.com/")
        self.assertTrue(report.not_needed == 1)


class TestCacheHitSecondRun(EnrichmentSqliteFixture):
    def test_second_run_uses_cache_without_network(self) -> None:
        config = EnrichmentConfig(search_enabled=True)
        search = _CountingSearch(["https://radiantplumbing.com/"])

        seeds1, _ = run_enrichment(
            self.connection,
            [seed()],
            config,
            search_client=search,
            fetcher=lambda url: matching_page(),
        )
        self.assertEqual(search.calls, 1)

        seeds2, report = run_enrichment(
            self.connection,
            [seed()],
            config,
            search_client=search,
            fetcher=lambda url: matching_page(),
        )
        self.assertEqual(search.calls, 1)
        self.assertEqual(seeds2[0].url, seeds1[0].url)
        self.assertEqual(seeds2[0].enrichment_status, "found")
        self.assertTrue(report.found == 1)


class TestApplyEnrichmentToExisting(EnrichmentSqliteFixture):
    def test_no_match_means_no_db_touch(self) -> None:
        apply_enrichment_to_existing(
            self.connection,
            business_name="Radiant Plumbing",
            city="Austin",
            state="TX",
            category="plumber",
            website_url="https://radiantplumbing.com/",
            status="found",
            source="web_search",
            confidence=0.9,
            last_error=None,
            checked_at="2026-01-01 00:00:00",
        )
        rows = self.connection.execute("SELECT id FROM leads").fetchall()
        self.assertEqual(rows, [])

    def test_url_keyed_row_just_refreshed(self) -> None:
        upsert_lead(
            self.connection,
            LeadUpsert(
                website_url="https://radiantplumbing.com/",
                business_name="Radiant Plumbing",
                city="Austin",
                state="TX",
                category="plumber",
            ),
        )
        apply_enrichment_to_existing(
            self.connection,
            business_name="Radiant Plumbing",
            city="Austin",
            state="TX",
            category="plumber",
            website_url="https://radiantplumbing.com/",
            status="found",
            source="web_search",
            confidence=0.85,
            last_error=None,
            checked_at="2026-01-01 00:00:00",
        )
        row = self.connection.execute(
            "SELECT enrichment_status, enrichment_confidence FROM leads"
        ).fetchone()
        self.assertEqual(row[0], "found")
        self.assertEqual(row[1], 0.85)


if __name__ == "__main__":
    unittest.main()