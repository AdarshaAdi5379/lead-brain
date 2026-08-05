"""Tests for the context builder (src/chat/context_builder.py)."""

from __future__ import annotations

import unittest

from src.chat.base import RetrievedContext, RetrievedLead
from src.chat.context_builder import build_context_block, build_lead_block


class ContextBuilderTests(unittest.TestCase):
    def test_build_lead_block_none_for_missing_lead(self) -> None:
        self.assertIsNone(build_lead_block({}))
        self.assertIsNotNone(build_lead_block({"lead": {"business_name": "X"}}))

    def test_build_lead_block_contains_key_facts(self) -> None:
        intel = {
            "lead": {
                "business_name": "Joe's Pizzeria",
                "category": "Restaurant",
                "city": "Austin",
                "state": "TX",
                "website_url": "https://joes.example.com",
                "phone": "512-555-0142",
            },
            "score": {
                "final_score": 81,
                "priority_label": "Hot",
                "top_positive_reasons": ["Strong local presence"],
                "top_negative_reasons": ["Outdated site"],
                "recommended_outreach_angle": "Offer a redesign",
            },
            "seo": {"site_score": 35, "overall_health": "poor"},
            "visual": {"visual_score": 40, "visual_health_label": "weak"},
            "opportunities": [
                {"label": "Website redesign", "score": 80, "evidence": ["Outdated design"]}
            ],
        }
        block = build_lead_block(intel)
        self.assertIsNotNone(block)
        for needle in (
            "Joe's Pizzeria",
            "Restaurant",
            "Austin",
            "81",
            "35",
            "Website redesign",
            "Offer a redesign",
        ):
            self.assertIn(needle, block)

    def test_build_context_block_respects_max_chars(self) -> None:
        intel = {"lead": {"business_name": "X" * 400}}
        context = RetrievedContext(
            query="q",
            retrieved_leads=[RetrievedLead(lead_id=i, intel=intel) for i in range(1, 12)],
        )
        body = build_context_block(context, max_leads=11, max_chars=1000)
        self.assertLessEqual(len(body), 1800)
        self.assertIn("omitted", body)

    def test_build_context_block_empty(self) -> None:
        context = RetrievedContext(query="q")
        self.assertEqual(build_context_block(context, max_leads=8, max_chars=24000), "")

    def test_build_context_block_trims_to_max_leads(self) -> None:
        intel = {"lead": {"business_name": "Biz"}}
        context = RetrievedContext(
            query="q",
            retrieved_leads=[RetrievedLead(lead_id=i, intel=intel) for i in range(1, 21)],
        )
        body = build_context_block(context, max_leads=5, max_chars=10_000_000)
        self.assertLess(body.count("Biz"), 8)

    def test_rationale_displayed_in_blocks(self) -> None:
        intel = {"lead": {"business_name": "Biz"}}
        context = RetrievedContext(
            query="q",
            retrieved_leads=[
                RetrievedLead(lead_id=1, intel=intel, rationale="matched weak seo filter")
            ],
        )
        self.assertIn("matched weak seo filter", build_context_block(context, max_leads=5, max_chars=10_000_000))


if __name__ == "__main__":
    unittest.main()