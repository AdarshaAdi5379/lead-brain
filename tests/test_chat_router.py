"""Tests for the deterministic query router (src/chat/router.py)."""

from __future__ import annotations

import unittest

from src.chat.base import Intent
from src.chat.router import RouteHints, route_query


class RouterIntentTests(unittest.TestCase):
    def test_empty_query_defaults_to_search(self) -> None:
        route = route_query("   ")
        self.assertEqual(route.intent, Intent.SEARCH)

    def test_similar_intent(self) -> None:
        for query in (
            "Find businesses similar to Joe's Pizzeria",
            "more leads like Bella Trattoria",
            "show me something like this",
        ):
            with self.subTest(query=query):
                self.assertEqual(route_query(query).intent, Intent.SIMILAR)

    def test_detail_intent(self) -> None:
        self.assertEqual(route_query("Tell me about Joe's Diner").intent, Intent.DETAIL)

    def test_compare_intent(self) -> None:
        for query in ("Compare the top two restaurants", "Joe's vs Bella"):
            with self.subTest(query=query):
                self.assertEqual(route_query(query).intent, Intent.COMPARE)

    def test_summarize_intent(self) -> None:
        self.assertEqual(
            route_query("Summarize the top 10 most promising leads").intent, Intent.SUMMARIZE
        )

    def test_explain_intent(self) -> None:
        self.assertEqual(route_query("Why did this lead score so high?").intent, Intent.EXPLAIN)

    def test_outreach_intent(self) -> None:
        for query in (
            "Which leads should I message first?",
            "easiest to pitch redesign services to",
        ):
            with self.subTest(query=query):
                self.assertEqual(route_query(query).intent, Intent.OUTREACH)

    def test_rank_intent(self) -> None:
        for query in ("What are the best opportunities?", "show me the strongest leads"):
            with self.subTest(query=query):
                self.assertEqual(route_query(query).intent, Intent.RANK)

    def test_plain_question_is_search(self) -> None:
        self.assertEqual(route_query("Show me plumbers").intent, Intent.SEARCH)

    def test_top_n_extraction(self) -> None:
        route = route_query("top 5 restaurants")
        self.assertEqual(route.params.get("top_n"), 5)
        route = route_query("first 3 businesses")
        self.assertEqual(route.params.get("top_n"), 3)

    def test_priority_band_extraction(self) -> None:
        self.assertEqual(route_query("show hot leads").params.get("priority"), "Hot")
        self.assertEqual(route_query("cold leads").params.get("priority"), "Cold")

    def test_threshold_extraction(self) -> None:
        route = route_query("redesign opportunity above 80")
        self.assertEqual(route.params.get("opportunity_score"), {"min": 80})
        route = route_query("seo above 70")
        self.assertEqual(route.params.get("seo_score"), {"min": 70})

    def test_weak_seo_signal(self) -> None:
        route = route_query("businesses with weak seo")
        self.assertEqual(route.params.get("seo_score"), {"max": 60})

    def test_weak_visual_signal(self) -> None:
        route = route_query("outdated website design")
        self.assertEqual(route.params.get("visual_score"), {"max": 60})

    def test_no_website_signal(self) -> None:
        self.assertEqual(route_query("leads with no website").params.get("website_present"), False)

    def test_platform_extraction(self) -> None:
        self.assertEqual(route_query("wordpress sites").params.get("platform"), "wordpress")
        self.assertEqual(route_query("wix").params.get("platform"), "wix")

    def test_place_extraction_from_hints(self) -> None:
        hints = RouteHints(
            categories=("Restaurant",),
            cities=("Bangalore",),
            states=("TX",),
            countries=("India",),
        )
        route = route_query("restaurants in Bangalore", hints=hints)
        self.assertEqual(route.params.get("category"), "Restaurant")
        self.assertEqual(route.params.get("city"), "Bangalore")

    def test_business_name_extraction(self) -> None:
        hints = RouteHints(business_names=("ABC Plumbing",))
        route = route_query("show me ABC Plumbing", hints=hints)
        self.assertEqual(route.params.get("business_name"), "ABC Plumbing")

    def test_business_name_dropped_outside_detail_similar_compare(self) -> None:
        hints = RouteHints(business_names=("ABC Plumbing",))
        route = route_query("summarize ABC Plumbing", hints=hints)
        self.assertNotIn("business_name", route.params)

    def test_business_name_kept_for_compare(self) -> None:
        hints = RouteHints(business_names=("ABC Plumbing", "Bella Trattoria"))
        route = route_query("compare ABC Plumbing and Bella Trattoria", hints=hints)
        self.assertEqual(route.params.get("business_name"), "ABC Plumbing")
        self.assertEqual(route.params.get("business_names"), ["Bella Trattoria"])

    def test_business_name_taken_from_phrase(self) -> None:
        route = route_query("tell me about Moonlight Cafe")
        self.assertEqual(route.params.get("business_name").lower(), "moonlight cafe")
        self.assertEqual(route.intent, Intent.DETAIL)


if __name__ == "__main__":
    unittest.main()