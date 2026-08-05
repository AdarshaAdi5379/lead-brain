"""Outreach context builder tests: shape, fact coverage, NULL safety."""

from __future__ import annotations

import unittest

from src.outreach.context import (
    build_outreach_context,
    outreach_context_for_lead,
    outreach_context_text,
)
from src.storage import search as search_storage

from tests.search_fixtures import SearchTestDb


class TestOutreachContext(unittest.TestCase):
    def setUp(self) -> None:
        self.db = SearchTestDb()
        self.connection = self.db.connection

    def tearDown(self) -> None:
        self.db.close()

    def _intel(self, lead_id: int) -> dict:
        intel = search_storage.lead_intelligence(self.connection, lead_id)
        assert intel is not None
        return intel

    def test_returns_none_without_lead(self) -> None:
        self.assertIsNone(build_outreach_context({}))
        self.assertIsNone(build_outreach_context({"seo": {}}))

    def test_rich_lead_context(self) -> None:
        lead_id = self.db.add_lead(
            name="Taco Stand", website="https://taco.com", category="Restaurant",
            city="Austin", state="TX", country="US", platform="WordPress",
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
            contact_page_url="https://taco.com/contact",
            contact_form_url="https://taco.com/contact-form",
            google_maps_url="https://maps.example.com/x",
            service_areas=["Austin", "Round Rock"],
        )
        self.db.add_detection(lead_id, "WordPress")
        self.db.add_seo(lead_id, 35, "poor")
        self.db.add_visual(lead_id, 40)
        self.db.add_score(lead_id, 62, "Warm")
        self.db.add_opportunity(lead_id, "Redesign", 85, ["Outdated design"])
        self.db.connection.execute(
            "UPDATE visual_audits SET total_pages_audited = 3,"
            " pages_with_weak_mobile_signal = 1, pages_with_modern_design_signal = 0"
            " WHERE lead_id = ?",
            (lead_id,),
        )
        self.db.connection.execute(
            "UPDATE business_opportunities SET recommended_services_json = ? WHERE lead_id = ?",
            ('["Redesign"]', lead_id),
        )
        self.db.connection.commit()

        context = build_outreach_context(self._intel(lead_id))
        assert context is not None
        self.assertEqual(context["business"]["business_name"], "Taco Stand")
        self.assertEqual(context["location"]["postal_code"], "75039")
        self.assertEqual(context["services"], ["Austin", "Round Rock"])
        self.assertEqual(context["contact"]["owner_name"], "Joy")
        self.assertEqual(context["contact"]["email"], "joy@taco.com")
        self.assertEqual(context["social_presence"]["whatsapp"], "https://wa.me/15550100")
        self.assertEqual(context["opening_hours"], "Mon-Fri 9am-5pm")
        self.assertEqual(context["seo"]["site_score"], 35)
        self.assertEqual(context["visual"]["visual_score"], 40)
        self.assertEqual(context["opportunity_summary"]["top_opportunity"], "Redesign")
        self.assertEqual(context["opportunity_summary"]["count"], 1)
        self.assertTrue(context["reachability"]["email"])
        self.assertEqual(context["reachability"]["best_contact_method"], "email")
        self.assertEqual(context["lead_score"], 62)
        self.assertEqual(context["priority"], "Warm")
        self.assertTrue(context["recommended_outreach_angle"])
        self.assertIn("Weak SEO score", context["top_seo_issues"])
        self.assertIn("Weak mobile experience", context["top_visual_issues"])
        self.assertIn("Outdated design", context["top_visual_issues"])
        self.assertEqual(context["top_opportunities"][0]["label"], "Redesign")
        self.assertEqual(context["top_opportunities"][0]["recommended_services"], ["Redesign"])
        self.assertIn("Taco Stand", context["business_summary"])

    def test_reachability_priority_order(self) -> None:
        lead_id = self.db.add_lead(name="All Channels", website="https://all.com")
        self.db.add_contact(
            lead_id,
            email="a@b.com",
            linkedin_url="https://linkedin.com/x",
            facebook_url="https://fb.com/x",
            whatsapp_url="https://wa.me/1",
            contact_form_url="https://all.com/form",
            phone="111",
        )
        context = build_outreach_context(self._intel(lead_id))
        assert context is not None
        self.assertEqual(context["reachability"]["best_contact_method"], "email")

    def test_reachability_falls_back_to_lower_priority(self) -> None:
        lead_id = self.db.add_lead(name="Phone Only", website=None)
        self.db.add_contact(lead_id, phone="111")
        context = build_outreach_context(self._intel(lead_id))
        assert context is not None
        self.assertEqual(context["reachability"]["best_contact_method"], "phone")

    def test_no_reachability(self) -> None:
        lead_id = self.db.add_lead(name="Bare Co", website=None)
        context = build_outreach_context(self._intel(lead_id))
        assert context is not None
        self.assertIsNone(context["reachability"].get("best_contact_method"))

    def test_empties_are_dropped(self) -> None:
        lead_id = self.db.add_lead(name="Bare Co", website=None)
        context = build_outreach_context(self._intel(lead_id))
        assert context is not None
        self.assertEqual(context["contact"], {})
        self.assertEqual(context["social_presence"], {})
        self.assertEqual(context["services"], [])
        self.assertEqual(context["opportunity_summary"]["count"], 0)

    def test_text_render_is_neutral_and_complete(self) -> None:
        context = {
            "business": {"business_name": "Taco Stand", "category": "Restaurant"},
            "location": {"city": "Austin", "state": "TX", "postal_code": "75039"},
            "services": ["Austin"],
            "contact": {"email": "joy@taco.com", "website_url": "https://taco.com"},
            "social_presence": {"instagram": "https://ig.com/taco"},
            "opening_hours": "Mon-Fri 9am-5pm",
            "technology": {"platform": "WordPress", "detections": []},
            "seo": {"site_score": 35, "overall_health": "poor"},
            "visual": {"visual_score": 40, "visual_health_label": "needs_work"},
            "opportunity_summary": {
                "count": 1,
                "opportunity_score": 85,
                "top_opportunity": "Redesign",
                "recommended_services": ["Redesign"],
            },
            "reachability": {"email": True},
        }
        text = outreach_context_text(context)
        for needle in (
            "Taco Stand", "75039", "Austin", "joy@taco.com", "https://taco.com",
            "instagram", "Mon-Fri", "WordPress", "35/100", "40/100", "Redesign",
        ):
            self.assertIn(needle, text)

    def test_for_lead_loader(self) -> None:
        lead_id = self.db.add_lead(name="Taco Stand", website="https://taco.com")
        self.db.add_contact(lead_id, email="a@b.com")
        context = outreach_context_for_lead(self.connection, lead_id)
        assert context is not None
        self.assertEqual(context["contact"]["email"], "a@b.com")
        self.assertIsNone(outreach_context_for_lead(self.connection, 9999))


if __name__ == "__main__":
    unittest.main()