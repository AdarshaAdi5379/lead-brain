"""End-to-end SearchService tests: search modes, filters, similar, context."""

from __future__ import annotations

import unittest

from src.search.query import SearchError, SearchQuery
from src.search.search_service import SearchService

from tests.search_fixtures import SearchTestDb, test_config


def _seed(db: SearchTestDb) -> None:
    """Three distinct, rich leads."""
    db.add_lead(
        name="Papa's Pizza", website="https://papaspizza.com", category="Restaurant",
        city="Austin", state="TX", country="US", platform="WordPress",
        priority="Hot", score=78,
    )
    db.add_lead(
        name="Dallas Plumbing Co", website="https://dallasplumbing.com", category="Plumber",
        city="Dallas", state="TX", country="US", platform="Wix",
        priority="Warm", score=55,
    )
    db.add_lead(
        name="Frosty Bakery", website="https://frostybakery.com", category="Restaurant",
        city="Austin", state="TX", country="US", platform="Wix",
        priority="Cold", score=30,
    )


class TestSearchServiceSearch(unittest.TestCase):
    def setUp(self) -> None:
        self.db = SearchTestDb()
        self.service = SearchService(self.db.path, config=test_config())
        _seed(self.db)
        self.service.index_run(self.db.run_id)

    def tearDown(self) -> None:
        self.db.close()

    def test_semantic_search_returns_all_indexed(self) -> None:
        results = self.service.search(SearchQuery(text="pizza restaurant", mode="semantic"))
        self.assertEqual(len(results), 3)
        self.assertEqual(results[0].business_name, "Papa's Pizza")
        self.assertGreater(results[0].similarity, results[1].similarity)

    def test_keyword_search(self) -> None:
        results = self.service.search(SearchQuery(text="bakery", mode="keyword"))
        self.assertEqual([r.business_name for r in results], ["Frosty Bakery"])

    def test_hybrid_is_default(self) -> None:
        results = self.service.search(SearchQuery(text="bakery"))
        self.assertEqual(results[0].business_name, "Frosty Bakery")
        self.assertGreaterEqual(results[0].combined_score, 0.0)

    def test_result_card_fields(self) -> None:
        results = self.service.search(SearchQuery(text="plumbing", mode="keyword"))
        result = results[0]
        self.assertEqual(result.lead_id, 2)
        self.assertEqual(result.business_name, "Dallas Plumbing Co")
        self.assertEqual(result.city, "Dallas")
        self.assertEqual(result.state, "TX")
        self.assertEqual(result.country, "US")
        self.assertEqual(result.platform, "Wix")
        self.assertEqual(result.priority, "Warm")
        self.assertEqual(result.lead_score, 55)
        self.assertIn(result.website_url, ("https://dallasplumbing.com", "https://dallasplumbing.com/"))

    def test_filters_apply(self) -> None:
        results = self.service.search(
            SearchQuery(text="", mode="semantic", filters={"category": "Restaurant"})
        )
        self.assertEqual({r.business_name for r in results}, {"Papa's Pizza", "Frosty Bakery"})

    def test_range_filter(self) -> None:
        results = self.service.search(
            SearchQuery(
                text="", mode="semantic",
                filters={"lead_score": {"min": 50}},
            )
        )
        self.assertEqual({r.business_name for r in results}, {"Papa's Pizza", "Dallas Plumbing Co"})

    def test_priority_filter(self) -> None:
        results = self.service.search(
            SearchQuery(text="", mode="semantic", filters={"priority": "Hot"})
        )
        self.assertEqual([r.business_name for r in results], ["Papa's Pizza"])

    def test_combined_filters(self) -> None:
        results = self.service.search(
            SearchQuery(
                text="", mode="semantic",
                filters={"category": "Restaurant", "city": "Austin"},
            )
        )
        self.assertEqual({r.business_name for r in results}, {"Papa's Pizza", "Frosty Bakery"})

    def test_malformed_filters_raise_search_error(self) -> None:
        with self.assertRaises(SearchError):
            self.service.search(SearchQuery(text="x", filters={"nope": 1}))

    def test_top_k_limit(self) -> None:
        results = self.service.search(SearchQuery(text="", mode="semantic", top_k=2))
        self.assertLessEqual(len(results), 2)

    def test_empty_index_returns_empty(self) -> None:
        from tests.search_fixtures import SearchTestDb as FreshDb
        empty_db = FreshDb()
        try:
            service = SearchService(empty_db.path, config=test_config())
            self.assertEqual(
                service.search(SearchQuery(text="anything", mode="semantic")), []
            )
        finally:
            empty_db.close()

    def test_search_uses_top_opportunity_score(self) -> None:
        lead_id = 3
        self.db.add_score(lead_id, 30, "Cold", positive=["Bakery"], negative=["No reviews"])
        self.db.add_opportunity(lead_id, "Online ordering", 90, ["No ordering"])
        self.service.update_lead(lead_id)
        results = self.service.search(SearchQuery(text="bakery", mode="keyword"))
        self.assertEqual(results[0].opportunity_score, 90)
        self.assertEqual(results[0].top_reasons[0], "Bakery")


class TestSearchServiceSimilar(unittest.TestCase):
    def setUp(self) -> None:
        self.db = SearchTestDb()
        self.service = SearchService(self.db.path, config=test_config())
        _seed(self.db)
        self.service.index_run(self.db.run_id)

    def tearDown(self) -> None:
        self.db.close()

    def test_similar_excludes_self(self) -> None:
        results = self.service.similar(1, top_k=10)
        self.assertNotIn(1, [r.lead_id for r in results])
        self.assertEqual(len(results), 2)

    def test_similar_orders_by_similarity(self) -> None:
        results = self.service.similar(1, top_k=10)
        self.assertEqual(results[0].lead_id, 3)
        self.assertGreaterEqual(results[0].similarity, results[1].similarity)

    def test_similar_unknown_lead_raises(self) -> None:
        with self.assertRaises(SearchError):
            self.service.similar(999, top_k=5)

    def test_similar_empty_index(self) -> None:
        solo_db = SearchTestDb()
        try:
            service = SearchService(solo_db.path, config=test_config())
            solo_db.add_lead(name="Solo", website="https://solo.com")
            service.index_run(solo_db.run_id)
            self.assertEqual(service.similar(1, top_k=5), [])
        finally:
            solo_db.close()


class TestSearchServiceContext(unittest.TestCase):
    def setUp(self) -> None:
        self.db = SearchTestDb()
        self.service = SearchService(self.db.path, config=test_config())
        self.lead_id = self.db.add_lead(
            name="Papa's Pizza", website="https://papaspizza.com", category="Restaurant",
            city="Austin", state="TX", country="US", platform="WordPress",
            priority="Hot", score=78,
        )
        self.db.add_seo(self.lead_id, 35, "poor", ["No meta descriptions"])
        self.db.add_opportunity(self.lead_id, "Redesign", 85, ["Old site"])

    def tearDown(self) -> None:
        self.db.close()

    def test_context_for_lead(self) -> None:
        context = self.service.context_for_lead(self.lead_id)
        assert context is not None
        self.assertEqual(context["business"]["business_name"], "Papa's Pizza")
        self.assertEqual(context["opportunities"]["top_opportunity"], "Redesign")

    def test_context_text(self) -> None:
        text = self.service.context_text_for_lead(self.lead_id)
        assert text is not None
        self.assertIn("Papa's Pizza", text)
        self.assertIn("Redesign", text)

    def test_context_unknown_lead(self) -> None:
        self.assertIsNone(self.service.context_for_lead(999))
        self.assertIsNone(self.service.context_text_for_lead(999))


class TestSearchServiceStats(unittest.TestCase):
    def setUp(self) -> None:
        self.db = SearchTestDb()
        self.service = SearchService(self.db.path, config=test_config())

    def tearDown(self) -> None:
        self.db.close()

    def test_stats_and_count(self) -> None:
        self.assertEqual(self.service.count(), 0)
        self.db.add_lead(name="A", website="https://a.com")
        self.service.index_run(self.db.run_id)
        stats = self.service.stats()
        self.assertEqual(stats["count"], 1)
        self.assertEqual(stats["enabled"], True)
        self.assertEqual(stats["vector_store"], "SqliteVectorStore")

    def test_service_initializes_missing_db(self) -> None:
        import tempfile
        from pathlib import Path
        path = Path(tempfile.mktemp(suffix=".sqlite"))
        service = SearchService(path, config=test_config())
        self.assertEqual(service.count(), 0)
        if path.exists():
            path.unlink()


if __name__ == "__main__":
    unittest.main()
