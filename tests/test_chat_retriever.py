"""Tests for the retrieval layer (src/chat/retriever.py)."""

from __future__ import annotations

import unittest

from src.chat.base import Intent, RetrievalStrategy
from src.chat.retriever import LeadRetriever
from tests.chat_fixtures import SearchTestDb, chat_config


class RetrieverTests(unittest.TestCase):
    def setUp(self) -> None:
        self.db = SearchTestDb()
        self.pizzerias = self.db.add_lead(
            name="Joe's Pizzeria", website="https://joes.example.com",
            category="Restaurant", city="Austin", platform="wordpress", priority="Hot",
        )
        self.bella = self.db.add_lead(
            name="Bella Trattoria", website="https://bella.example.org",
            category="Restaurant", city="Austin", platform="wordpress", priority="Warm",
        )
        self.plumber = self.db.add_lead(
            name="Fix-It Plumbing", category="Plumber", city="Dallas", state="TX",
        )
        self.db.add_detection(self.pizzerias, "WordPress", "cms")
        self.db.add_score(self.pizzerias, final_score=81, priority_label="Hot")
        self.db.add_score(self.bella, final_score=42, priority_label="Warm")
        self.db.add_seo(self.pizzerias, site_score=35, overall_health="poor")
        self.db.add_seo(self.bella, site_score=88, overall_health="good")
        self.db.add_visual(self.pizzerias, visual_score=40)
        self.db.add_opportunity(self.pizzerias, label="Website redesign", score=80)

    def tearDown(self) -> None:
        self.db.close()

    def retriever(self) -> LeadRetriever:
        return LeadRetriever(self.db.path, chat_config())

    def test_hints_from_database(self) -> None:
        hints = self.retriever().hints()
        self.assertIn("Restaurant", hints.categories)
        self.assertIn("Austin", hints.cities)
        self.assertIn("Joe's Pizzeria", hints.business_names)

    def test_sql_filters_strategy_when_index_empty(self) -> None:
        context = self.retriever().search("restaurants")
        self.assertEqual(context.strategy, RetrievalStrategy.SQL_FILTERS)
        self.assertEqual(
            {lead.lead_id for lead in context.retrieved_leads},
            {self.pizzerias, self.bella, self.plumber},
        )

    def test_category_filter(self) -> None:
        context = self.retriever().search("", filters={"category": ["Plumber"]})
        ids = [lead.lead_id for lead in context.retrieved_leads]
        self.assertEqual(ids, [self.plumber])

    def test_city_filter(self) -> None:
        context = self.retriever().search("", filters={"city": ["Austin"]})
        ids = [lead.lead_id for lead in context.retrieved_leads]
        self.assertNotIn(self.plumber, ids)

    def test_score_range_filter(self) -> None:
        context = self.retriever().search("", filters={"lead_score": {"min": 50}})
        ids = [lead.lead_id for lead in context.retrieved_leads]
        self.assertIn(self.pizzerias, ids)
        self.assertNotIn(self.bella, ids)

    def test_seo_range_filter(self) -> None:
        context = self.retriever().search("", filters={"seo_score": {"max": 60}})
        self.assertEqual([lead.lead_id for lead in context.retrieved_leads], [self.pizzerias])

    def test_opportunity_range_filter(self) -> None:
        context = self.retriever().search("", filters={"opportunity_score": {"min": 75}})
        self.assertEqual([lead.lead_id for lead in context.retrieved_leads], [self.pizzerias])

    def test_website_present_filter(self) -> None:
        context = self.retriever().search("", filters={"website_present": False})
        self.assertEqual([lead.lead_id for lead in context.retrieved_leads], [self.plumber])

    def test_technology_filter(self) -> None:
        context = self.retriever().search("", filters={"technologies": ["WordPress"]})
        self.assertEqual([lead.lead_id for lead in context.retrieved_leads], [self.pizzerias])

    def test_ordering_by_lead_score_desc(self) -> None:
        context = self.retriever().search("")
        scores = [
            (lead.intel.get("score") or {}).get("final_score")
            for lead in context.retrieved_leads
        ]
        known = [score for score in scores if score is not None]
        self.assertEqual(known, sorted(known, reverse=True))
        self.assertIn(None, scores)

    def test_retrieve_route_with_weak_seo(self) -> None:
        route = self.retriever().route("businesses with weak seo")
        context = self.retriever().retrieve(route)
        self.assertEqual(context.strategy, RetrievalStrategy.SQL_FILTERS)
        self.assertEqual([lead.lead_id for lead in context.retrieved_leads], [self.pizzerias])

    def test_retrieve_detail_by_name(self) -> None:
        route = self.retriever().route("Tell me about Joe's Pizzeria")
        context = self.retriever().retrieve(route)
        self.assertEqual(context.strategy, RetrievalStrategy.LEAD_DETAIL)
        self.assertEqual(context.retrieved_leads[0].lead_id, self.pizzerias)
        self.assertGreater(len(context.retrieved_leads[0].intel), 0)

    def test_retrieve_detail_by_lead_id(self) -> None:
        from src.chat.base import IntentRoute

        route = IntentRoute(intent=Intent.DETAIL, params={"lead_id": self.bella})
        context = self.retriever().retrieve(route)
        self.assertEqual(context.retrieved_leads[0].lead_id, self.bella)

    def test_retrieve_unknown_detail_is_empty(self) -> None:
        route = self.retriever().route("Tell me about Moonlight Cafe")
        context = self.retriever().retrieve(route)
        self.assertTrue(context.is_empty)

    def test_similar_sql_fallback_ranks_same_category_first(self) -> None:
        context = self.retriever().similar(self.pizzerias, top_k=5)
        self.assertEqual(context.strategy, RetrievalStrategy.SIMILARITY)
        ids = [lead.lead_id for lead in context.retrieved_leads]
        self.assertEqual(ids[0], self.bella)

    def test_context_for_lead_ids_missing_leads_skipped(self) -> None:
        context = self.retriever().context_for_lead_ids(
            [self.pizzerias, 9999], strategy=RetrievalStrategy.COMPARE
        )
        self.assertEqual(len(context.retrieved_leads), 1)

    def test_compare_by_business_names(self) -> None:
        route = self.retriever().route("compare Joe's Pizzeria and Bella Trattoria")
        context = self.retriever().retrieve(route)
        self.assertEqual(context.strategy, RetrievalStrategy.COMPARE)
        self.assertEqual(len(context.retrieved_leads), 2)

    def test_compare_by_filters_when_no_names(self) -> None:
        route = self.retriever().route("compare the top two restaurants")
        context = self.retriever().retrieve(route)
        self.assertEqual(context.strategy, RetrievalStrategy.COMPARE)
        self.assertGreaterEqual(len(context.retrieved_leads), 2)

    def test_filters_merge_ui_wins(self) -> None:
        context = self.retriever().search(
            "", filters={"category": ["Restaurant"], "city": ["Dallas"]}
        )
        self.assertTrue(context.is_empty)

    def test_intelligence_has_expected_keys(self) -> None:
        context = self.retriever().search("")
        intel = context.retrieved_leads[0].intel
        self.assertIn("score", intel)
        self.assertIn("seo", intel)
        self.assertIn("opportunities", intel)

    def test_index_count_zero_without_embeddings(self) -> None:
        self.assertEqual(self.retriever().index_count(), 0)


if __name__ == "__main__":
    unittest.main()