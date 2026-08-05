"""Tests for the answer generator (src/chat/response.py)."""

from __future__ import annotations

import unittest

from src.chat.base import (
    ChatMode,
    Intent,
    IntentRoute,
    RetrievalStrategy,
    RetrievedContext,
    RetrievedLead,
)
from src.chat.response import ResponseGenerator
from tests.chat_fixtures import FakeLLMBackend, SearchTestDb, chat_config


INTEL = {
    "lead": {
        "business_name": "Joe's Pizzeria",
        "category": "Restaurant",
        "city": "Austin",
        "state": "TX",
    },
    "score": {"final_score": 81, "priority_label": "Hot"},
    "seo": {"site_score": 35, "overall_health": "poor"},
    "visual": {"visual_score": 40, "visual_health_label": "weak"},
    "opportunities": [{"label": "Website redesign", "score": 80}],
}
INTEL2 = {
    "lead": {
        "business_name": "Bella Trattoria",
        "category": "Restaurant",
        "city": "Austin",
        "state": "TX",
    },
    "score": {"final_score": 42, "priority_label": "Warm"},
    "seo": {"site_score": 88, "overall_health": "good"},
}


def context_for(*leads: tuple[int, dict]) -> RetrievedContext:
    return RetrievedContext(
        query="q",
        intent=Intent.SEARCH,
        strategy=RetrievalStrategy.SQL_FILTERS,
        retrieved_leads=[
            RetrievedLead(lead_id=lead_id, intel=intel, rationale="matched filters")
            for lead_id, intel in leads
        ],
    )


def route(intent: Intent = Intent.SEARCH) -> IntentRoute:
    return IntentRoute(intent=intent, raw_query="q")


class ResponseGeneratorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = chat_config()

    def generator(self, backend: FakeLLMBackend) -> ResponseGenerator:
        return ResponseGenerator(backend, self.config)

    def test_summary_mode_when_backend_unavailable(self) -> None:
        gen = self.generator(FakeLLMBackend(available=False))
        response = gen.generate(route(), context_for((1, INTEL), (2, INTEL2)))
        self.assertEqual(response.mode, ChatMode.RETRIEVAL_SUMMARY)
        self.assertTrue(response.grounded)
        self.assertIn("Joe's Pizzeria", response.answer)
        self.assertIn("Website redesign", response.answer)
        self.assertEqual(response.retrieved_lead_ids, [1, 2])

    def test_summary_never_calls_backend_when_unavailable(self) -> None:
        backend = FakeLLMBackend(available=False)
        self.generator(backend).generate(route(), context_for((1, INTEL)))
        self.assertEqual(backend.calls, [])

    def test_rag_mode_when_backend_grounded(self) -> None:
        backend = FakeLLMBackend("Joe's Pizzeria is the strongest lead with seo 35/100.")
        response = self.generator(backend).generate(route(), context_for((1, INTEL)))
        self.assertEqual(response.mode, ChatMode.RAG)
        self.assertTrue(response.grounded)
        self.assertIn("Joe's Pizzeria", response.answer)
        self.assertGreater(len(backend.calls), 0)

    def test_rag_falls_back_to_summary_on_hallucination(self) -> None:
        backend = FakeLLMBackend("Moon Cafe on Mars is the best redesign pick.")
        response = self.generator(backend).generate(route(), context_for((1, INTEL)))
        self.assertEqual(response.mode, ChatMode.RETRIEVAL_SUMMARY)
        self.assertIn("Joe's Pizzeria", response.answer)

    def test_rag_falls_back_on_empty_answer(self) -> None:
        backend = FakeLLMBackend(None)
        response = self.generator(backend).generate(route(), context_for((1, INTEL)))
        self.assertEqual(response.mode, ChatMode.RETRIEVAL_SUMMARY)

    def test_compare_renders_markdown_table(self) -> None:
        gen = self.generator(FakeLLMBackend(available=False))
        response = gen.generate(
            route(Intent.COMPARE), context_for((1, INTEL), (2, INTEL2))
        )
        self.assertIn("|---|", response.answer)
        self.assertIn("Joe's Pizzeria", response.answer)
        self.assertIn("Bella Trattoria", response.answer)

    def test_detail_renders_full_block(self) -> None:
        gen = self.generator(FakeLLMBackend(available=False))
        context = RetrievedContext(
            query="q",
            intent=Intent.DETAIL,
            strategy=RetrievalStrategy.LEAD_DETAIL,
            retrieved_leads=[RetrievedLead(lead_id=1, intel=INTEL, rationale="explicit")],
        )
        response = gen.generate(route(Intent.DETAIL), context)
        self.assertEqual(response.mode, ChatMode.LEAD_DETAIL)
        self.assertIn("Joe's Pizzeria", response.answer)

    def test_no_data_response_for_empty_context(self) -> None:
        gen = self.generator(FakeLLMBackend(available=True))
        context = context_for()
        response = gen.generate(route(), context)
        self.assertEqual(response.mode, ChatMode.NO_DATA)
        self.assertIn("I do not have enough data", response.answer)

    def test_sources_include_rationale_and_scores(self) -> None:
        gen = self.generator(FakeLLMBackend(available=False))
        response = gen.generate(route(), context_for((1, INTEL)))
        self.assertEqual(len(response.sources), 1)
        source = response.sources[0]
        self.assertEqual(source["lead_id"], 1)
        self.assertEqual(source["lead_score"], 81)
        self.assertEqual(source["seo_score"], 35)
        self.assertEqual(source["business_name"], "Joe's Pizzeria")


if __name__ == "__main__":
    unittest.main()