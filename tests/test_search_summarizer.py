"""AI context summarizer tests: structure, neutrality, missing-data safety."""

from __future__ import annotations

import unittest

from src.search.summarizer import build_context, context_to_text

from tests.search_fixtures import SearchTestDb


class TestBuildContext(unittest.TestCase):
    def setUp(self) -> None:
        self.db = SearchTestDb()
        self.connection = self.db.connection

    def tearDown(self) -> None:
        self.db.close()

    def _intel(self, lead_id: int) -> dict:
        from src.storage import search as search_storage
        intel = search_storage.lead_intelligence(self.connection, lead_id)
        assert intel is not None
        return intel

    def test_returns_none_without_lead(self) -> None:
        self.assertIsNone(build_context({}))
        self.assertIsNone(build_context({"seo": {}}))

    def test_rich_lead_context(self) -> None:
        lead_id = self.db.add_lead(
            name="Taco Stand", website="https://taco.com", category="Restaurant",
            city="Austin", state="TX", country="US", platform="WordPress",
            priority="Hot", score=75,
        )
        self.db.add_detection(lead_id, "WordPress")
        self.db.add_seo(lead_id, 35, "poor", ["No meta descriptions"])
        self.db.add_visual(lead_id, 40)
        self.db.add_score(lead_id, 70, "Hot", positive=["Good"], negative=["Old"])
        self.db.add_opportunity(lead_id, "Redesign", 85)

        context = build_context(self._intel(lead_id))
        assert context is not None
        self.assertEqual(context["business"]["business_name"], "Taco Stand")
        self.assertEqual(context["business"]["city"], "Austin")
        self.assertEqual(context["technology"]["platform"], "WordPress")
        self.assertEqual(context["technology"]["detections"][0]["name"], "WordPress")
        self.assertEqual(context["seo"]["site_score"], 35)
        self.assertEqual(context["visual"]["visual_score"], 40)
        self.assertEqual(context["opportunities"]["count"], 1)
        self.assertEqual(context["opportunities"]["top_opportunity"], "Redesign")
        self.assertEqual(context["opportunities"]["opportunity_score"], 85)
        self.assertEqual(context["scoring"]["final_score"], 70)
        self.assertEqual(context["scoring"]["priority_label"], "Hot")

    def test_minimal_lead_never_crashes(self) -> None:
        lead_id = self.db.add_lead(name="Bare Co", website=None)
        context = build_context(self._intel(lead_id))
        assert context is not None
        self.assertEqual(context["opportunities"]["count"], 0)
        self.assertEqual(context["opportunities"]["opportunity_score"], 0)
        self.assertEqual(context["seo"], {})
        self.assertEqual(context["visual"], {})
        self.assertEqual(context["social"], {})

    def test_contact_facts_in_context(self) -> None:
        lead_id = self.db.add_lead(
            name="Taco Stand", website="https://taco.com", category="Restaurant",
            city="Austin", state="TX", country="US",
        )
        self.db.add_contact(
            lead_id,
            owner_name="Joy",
            address="100 Main St",
            postal_code="75039",
            opening_hours="Mon-Fri 9am-5pm",
            phone="512-555-0100",
            email="joy@taco.com",
            whatsapp_url="https://wa.me/15550100",
            facebook_url="https://fb.com/taco",
            google_maps_url="https://maps.example.com/taco",
            service_areas=["Austin", "Round Rock"],
        )
        context = build_context(self._intel(lead_id))
        assert context is not None
        business = context["business"]
        self.assertEqual(business["owner_name"], "Joy")
        self.assertEqual(business["postal_code"], "75039")
        self.assertEqual(business["opening_hours"], "Mon-Fri 9am-5pm")
        self.assertEqual(business["google_maps_url"], "https://maps.example.com/taco")
        self.assertEqual(business["service_areas"], ["Austin", "Round Rock"])
        self.assertEqual(
            context["social"],
            {
                "facebook": "https://fb.com/taco",
                "whatsapp": "https://wa.me/15550100",
            },
        )


class TestContextToText(unittest.TestCase):
    def test_markdown_contains_neutral_sections(self) -> None:
        text = context_to_text(
            {
                "business": {"business_name": "Taco Stand", "city": "Austin", "state": "TX"},
                "technology": {"platform": "WordPress", "detections": []},
                "seo": {"site_score": 35, "overall_health": "poor"},
                "visual": {"visual_score": 40, "visual_health_label": "needs_work"},
                "opportunities": {
                    "count": 1,
                    "top_opportunity": "Redesign",
                    "opportunity_score": 85,
                    "items": [{"label": "Redesign", "score": 85, "evidence": []}],
                },
                "scoring": {"final_score": 70, "priority_label": "Hot"},
            }
        )
        self.assertIn("Taco Stand", text)
        self.assertIn("WordPress", text)
        self.assertIn("Redesign", text)

    def test_unknown_lead_label(self) -> None:
        text = context_to_text({"business": {}, "technology": {}, "opportunities": {}, "scoring": {}})
        self.assertIn("Business", text)

    def test_text_includes_contact_and_social(self) -> None:
        text = context_to_text(
            {
                "business": {
                    "business_name": "Taco Stand",
                    "city": "Austin",
                    "state": "TX",
                    "owner_name": "Joy",
                    "postal_code": "75039",
                    "opening_hours": "Mon-Fri 9am-5pm",
                    "service_areas": ["Austin"],
                    "google_maps_url": "https://maps.example.com/taco",
                },
                "social": {"whatsapp": "https://wa.me/15550100"},
                "technology": {"platform": "WordPress", "detections": []},
                "seo": {"site_score": 35, "overall_health": "poor"},
                "visual": {"visual_score": 40, "visual_health_label": "needs_work"},
                "opportunities": {
                    "count": 1,
                    "top_opportunity": "Redesign",
                    "opportunity_score": 85,
                    "items": [{"label": "Redesign", "score": 85, "evidence": []}],
                },
                "scoring": {"final_score": 70, "priority_label": "Hot"},
            }
        )
        for needle in (
            "Owner: Joy",
            "Postal code: 75039",
            "Opening hours: Mon-Fri 9am-5pm",
            "Service areas: Austin",
            "Maps: https://maps.example.com/taco",
            "## Social",
            "whatsapp: https://wa.me/15550100",
        ):
            self.assertIn(needle, text)


if __name__ == "__main__":
    unittest.main()
