from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from src.apify_entry import (
    _build_item,
    _build_seeds,
    _get_contact_methods,
    _has_contact,
    _visual_page_context,
)
from src.contact import ContactSignals
from src.fingerprinting.base import Detection
from src.fingerprinting.detector import FingerprintResult
from src.opportunities.base import Opportunity, OpportunityReport
from src.scoring.base import LeadScore
from src.url_loader import SeedRow
from src.visual.base import VisualAuditReport


class TestApifyEntry(unittest.TestCase):
    def test_build_seeds_with_urls(self) -> None:
        urls = ["https://site1.example.com", "https://site2.example.com"]
        seeds = _build_seeds(
            urls, "plumber", "Austin, TX", max_results=10, include_no_website=True
        )
        self.assertEqual(len(seeds), 2)
        self.assertEqual(seeds[0].url, "https://site1.example.com")
        self.assertEqual(seeds[0].city, "Austin")
        self.assertEqual(seeds[0].state, "TX")

    @patch("src.apify_entry.discover_to_seeds")
    def test_build_seeds_discovery_filter_no_website(self, mock_discover) -> None:
        mock_discover.return_value = [
            SeedRow(business_name="Site A", category="plumber", url="https://sitea.com", city="Austin", state="TX"),
            SeedRow(business_name="Site B", category="plumber", url="", city="Austin", state="TX"),
            SeedRow(business_name="Site C", category="plumber", url="https://sitec.com", city="Austin", state="TX"),
        ]
        seeds = _build_seeds(
            [], "plumber", "Austin, TX", max_results=10, include_no_website=False
        )
        self.assertEqual(len(seeds), 2)
        self.assertEqual(seeds[0].business_name, "Site A")
        self.assertEqual(seeds[1].business_name, "Site C")

    @patch("src.apify_entry.discover_to_seeds")
    def test_build_seeds_discovery_include_no_website(self, mock_discover) -> None:
        mock_discover.return_value = [
            SeedRow(business_name="Site A", category="plumber", url="https://sitea.com", city="Austin", state="TX"),
            SeedRow(business_name="Site B", category="plumber", url="", city="Austin", state="TX"),
        ]
        seeds = _build_seeds(
            [], "plumber", "Austin, TX", max_results=10, include_no_website=True, require_contact=False
        )
        self.assertEqual(len(seeds), 2)
        self.assertEqual(seeds[0].business_name, "Site A")
        self.assertEqual(seeds[1].business_name, "Site B")

    @patch("src.apify_entry.discover_to_seeds")
    def test_build_seeds_discovery_require_contact_filters_ghost_leads(self, mock_discover) -> None:
        mock_discover.return_value = [
            # Has website (kept for crawl)
            SeedRow(business_name="Site A", category="plumber", url="https://sitea.com", city="Austin", state="TX"),
            # No website, has phone (kept)
            SeedRow(business_name="Site B", category="plumber", url="", phone="+1-512-555-0199", city="Austin", state="TX"),
            # No website, has email (kept)
            SeedRow(business_name="Site C", category="plumber", url="", email="info@sitec.com", city="Austin", state="TX"),
            # No website, NO phone, NO email (ghost lead - dropped!)
            SeedRow(business_name="Ghost Co", category="plumber", url="", city="Austin", state="TX"),
        ]
        seeds = _build_seeds(
            [], "plumber", "Austin, TX", max_results=10, include_no_website=True, require_contact=True
        )
        self.assertEqual(len(seeds), 3)
        self.assertEqual([s.business_name for s in seeds], ["Site A", "Site B", "Site C"])

    def test_build_item_with_full_audits(self) -> None:
        seed = SeedRow(
            business_name="Acme Roofing",
            category="roofer",
            url="https://acmeroofing.example.com",
            city="Dallas",
            state="TX",
            phone="555-1234",
            email="info@acmeroofing.example.com",
        )
        lead_score = LeadScore(
            final_score=78,
            priority_label="Hot",
            dimension_scores={"seo_health": 40, "visual_presentation": 50},
            dimension_reasons={"seo_health": ["Poor SEO health (-20)"]},
            top_positive_reasons=["Location present (+20)"],
            top_negative_reasons=["Poor SEO health (-20)"],
            recommended_outreach_angle="Pitch responsive rebuild and local SEO.",
        )
        opp = Opportunity(
            category="website_redesign",
            label="Website Redesign",
            score=80,
            severity="High",
            confidence=85,
            evidence=("Outdated layout",),
            recommended_services=("Responsive Redesign", "Mobile Optimization"),
        )
        opp_report = OpportunityReport(
            opportunities=(opp,),
            top_opportunity="Website Redesign",
            top_opportunity_score=80,
            opportunity_count=1,
            opportunity_priority="High Revenue Potential",
        )
        seo_audit = SimpleNamespace(
            site_score=45,
            overall_health="Poor",
            severity_summary=(),
            pages=(),
        )
        visual_audit = VisualAuditReport(
            lead_url="https://acmeroofing.example.com",
            visual_score=60,
            visual_health_label="Fair",
            summary="Weak mobile layout and low contrast",
            total_pages_audited=1,
            pages_with_desktop_screenshot=1,
            pages_with_mobile_screenshot=1,
            pages_with_modern_design_signal=0,
            pages_with_clutter_signal=0,
            pages_with_weak_hierarchy_signal=0,
            pages_with_weak_mobile_signal=1,
            pages_with_weak_cta_signal=1,
            pages_with_strong_brand_signal=0,
        )
        contact = ContactSignals(
            phone="555-1234",
            email="info@acmeroofing.example.com",
            facebook_url="https://facebook.com/acmeroofing",
        )
        fingerprint = FingerprintResult(
            site_url="https://acmeroofing.example.com",
            detections=[
                Detection(name="WordPress", category="CMS", confidence=95),
            ],
        )

        item = _build_item(
            seed=seed,
            lead_score=lead_score,
            opportunity_report=opp_report,
            seo_audit=seo_audit,
            visual_audit=visual_audit,
            contact=contact,
            fingerprint=fingerprint,
            platform="wordpress",
        )

        self.assertEqual(item["business_name"], "Acme Roofing")
        self.assertTrue(item["has_website"])
        self.assertEqual(item["website_url"], "https://acmeroofing.example.com")
        self.assertEqual(item["platform"], "wordpress")
        self.assertEqual(len(item["technologies"]), 1)
        self.assertEqual(item["technologies"][0]["name"], "WordPress")
        self.assertEqual(item["seo_score"], 45)
        self.assertEqual(item["seo_health"], "Poor")
        self.assertEqual(item["visual_score"], 60)
        self.assertEqual(item["visual_health"], "Fair")
        self.assertIn("weak_mobile", item["visual_issues"])
        self.assertIn("weak_cta", item["visual_issues"])
        self.assertEqual(item["lead_score"], 78)
        self.assertEqual(item["priority"], "Hot")
        self.assertEqual(item["top_opportunity"], "Website Redesign")
        self.assertEqual(item["opportunity_count"], 1)
        self.assertIn("Responsive Redesign", item["recommended_services"])
        self.assertTrue(item["has_contact"])
        self.assertIn("phone", item["contact_methods"])
        self.assertIn("email", item["contact_methods"])

    def test_build_item_no_website_fallback_opportunities(self) -> None:
        seed = SeedRow(
            business_name="Aishwarya Interiors",
            category="interiors",
            url=None,
            city="Bangalore",
            state="",
            phone="+91 99654 82211",
        )
        lead_score = LeadScore(
            final_score=60,
            priority_label="Warm",
            dimension_scores={"discovery_quality": 70, "contactability": 50},
            dimension_reasons={"discovery_quality": ["Business category present (+20)"]},
            top_positive_reasons=["Business category present (+20)"],
            top_negative_reasons=["No website found"],
            recommended_outreach_angle="Establish contact first, then position a starter website.",
        )
        item = _build_item(
            seed=seed,
            lead_score=lead_score,
            opportunity_report=None,
            seo_audit=None,
            visual_audit=None,
            contact=ContactSignals(phone="+91 99654 82211"),
            fingerprint=None,
            platform=None,
        )

        self.assertEqual(item["business_name"], "Aishwarya Interiors")
        self.assertFalse(item["has_website"])
        self.assertIsNone(item["website_url"])
        self.assertIsNone(item["seo_score"])
        self.assertIsNone(item["visual_score"])
        # Crucial fix: opportunities and services must NOT be empty for no-website leads!
        self.assertEqual(item["top_opportunity"], "New Website Build")
        self.assertEqual(item["opportunity_count"], 1)
        self.assertTrue(len(item["opportunities"]) >= 1)
        self.assertEqual(item["opportunities"][0]["category"], "new_website_build")
        self.assertIn("Custom Starter Website", item["recommended_services"])

    def test_build_item_broken_website_recovery(self) -> None:
        seed = SeedRow(
            business_name="Broken Site Co",
            category="plumber",
            url="https://brokensite.example.com",
            city="Austin",
            state="TX",
            phone="555-9999",
        )
        lead_score = LeadScore(
            final_score=75,
            priority_label="Hot",
            dimension_scores={"outreach_potential": 90},
            dimension_reasons={"outreach_potential": ["Broken website"]},
            top_positive_reasons=["Website present (+15)"],
            top_negative_reasons=["Website unreachable (−30)"],
            recommended_outreach_angle="Website unreachable; pitch recovery rebuild.",
        )
        fetch = SimpleNamespace(success=False, error="net::ERR_NAME_NOT_RESOLVED")
        item = _build_item(
            seed=seed,
            lead_score=lead_score,
            opportunity_report=None,
            seo_audit=None,
            visual_audit=None,
            contact=ContactSignals(phone="555-9999"),
            fingerprint=None,
            platform=None,
            fetch=fetch,
        )
        self.assertEqual(item["top_opportunity"], "Website Recovery & Redesign")
        self.assertEqual(item["opportunity_count"], 1)
        self.assertEqual(item["opportunities"][0]["category"], "website_recovery")
        self.assertIn("Modern Website Rebuild", item["recommended_services"])

    def test_visual_page_context(self) -> None:
        page = SimpleNamespace(
            url="https://example.com/about",
            word_count=450,
            image_count=8,
        )
        seo_audit = SimpleNamespace(pages=(page,))
        ctx = _visual_page_context(
            SeedRow(business_name="Ex", category="", url="https://example.com", city="", state=""),
            None,
            seo_audit,
        )
        self.assertIn("https://example.com/about", ctx)
        self.assertEqual(ctx["https://example.com/about"]["word_count"], 450)
        self.assertEqual(ctx["https://example.com/about"]["image_count"], 8)


    def test_has_contact_and_contact_methods(self) -> None:
        self.assertTrue(_has_contact({"phone": "+1-512-555-0100"}))
        self.assertIn("phone", _get_contact_methods({"phone": "+1-512-555-0100"}))

        self.assertTrue(_has_contact({"email": "hello@example.com"}))
        self.assertIn("email", _get_contact_methods({"email": "hello@example.com"}))

        self.assertTrue(_has_contact({"socials": {"whatsapp": "https://wa.me/12345"}}))
        self.assertIn("whatsapp", _get_contact_methods({"socials": {"whatsapp": "https://wa.me/12345"}}))

        self.assertTrue(_has_contact({"contact_page_url": "https://example.com/contact"}))
        self.assertIn("contact_page", _get_contact_methods({"contact_page_url": "https://example.com/contact"}))

        self.assertTrue(_has_contact({"contact_form_url": "https://example.com/#form"}))
        self.assertIn("contact_form", _get_contact_methods({"contact_form_url": "https://example.com/#form"}))

        self.assertFalse(_has_contact({}))
        self.assertEqual(_get_contact_methods({}), [])
        self.assertFalse(_has_contact({"phone": None, "email": None, "socials": {}}))

    def test_build_item_without_contact(self) -> None:
        seed = SeedRow(
            business_name="Ghost Business",
            category="plumber",
            url=None,
            city="Austin",
            state="TX",
        )
        lead_score = LeadScore(
            final_score=60,
            priority_label="Warm",
            dimension_scores={},
            dimension_reasons={},
            top_positive_reasons=[],
            top_negative_reasons=[],
            recommended_outreach_angle="Pitch starter site.",
        )
        item = _build_item(
            seed=seed,
            lead_score=lead_score,
            opportunity_report=None,
            seo_audit=None,
            visual_audit=None,
            contact=ContactSignals(),
            fingerprint=None,
            platform=None,
        )
        self.assertFalse(item["has_contact"])
        self.assertEqual(item["contact_methods"], [])
        self.assertIsNone(item["phone"])
        self.assertIsNone(item["email"])


if __name__ == "__main__":
    unittest.main()
