import unittest

from src.opportunities import detect_opportunities
from src.opportunities.detectors import (
    detect_accessibility_improvement,
    detect_analytics_setup,
    detect_brand_refresh,
    detect_contact_funnel_improvement,
    detect_content_improvement,
    detect_conversion_optimization,
    detect_ecommerce_optimization,
    detect_hosting_upgrade,
    detect_local_seo,
    detect_maintenance_opportunity,
    detect_mobile_optimization,
    detect_performance_optimization,
    detect_security_improvement,
    detect_seo_improvement,
    detect_technical_modernization,
    detect_website_redesign,
)
from src.opportunities.config import default_config
from src.scoring.base import LeadScore, ScoringInputs
from src.scoring.config import ScoringConfig
from src.scoring.dimensions import (
    contactability,
    content_strength,
    discovery_quality,
    seo_health,
    technical_health,
    trust_professionalism,
)
from tests.opportunity_fixtures import ecommerce_inputs, legacy_platform_inputs
from tests.scoring_fixtures import no_website_inputs, strong_site_inputs, weak_site_inputs


def _score_for(signals: ScoringInputs) -> LeadScore:
    config = ScoringConfig()
    base = [
        discovery_quality(signals, config),
        contactability(signals, config),
        technical_health(signals, config),
        seo_health(signals, config),
        content_strength(signals, config),
        trust_professionalism(signals, config),
    ]
    dimension_scores = {r.name: r.score for r in base}
    return LeadScore(
        final_score=50,
        priority_label="Warm",
        dimension_scores=dimension_scores,
        dimension_reasons={r.name: list(r.reasons) for r in base},
        top_positive_reasons=[],
        top_negative_reasons=[],
        recommended_outreach_angle="Test",
    )


class TestOpportunityDetectors(unittest.TestCase):
    def setUp(self) -> None:
        self.config = default_config()
        self.strong = strong_site_inputs()
        self.weak = weak_site_inputs()
        self.legacy = legacy_platform_inputs()
        self.ecom = ecommerce_inputs()

    def _detect(self, detector, signals, lead_score=None):
        return detector(signals, lead_score or _score_for(signals), self.config)

    def test_analytics_setup_fires_only_without_analytics(self) -> None:
        item = self._detect(detect_analytics_setup, self.strong)
        self.assertIsNotNone(item)
        self.assertEqual(item.category, "analytics_setup")
        self.assertGreaterEqual(item.score, 70)

        with_analytics = self._detect(detect_analytics_setup, self.ecom)
        self.assertIsNone(with_analytics)

        no_site = self._detect(detect_analytics_setup, no_website_inputs())
        self.assertIsNone(no_site)

    def test_security_improvement_uses_https_and_mixed_content(self) -> None:
        https_clean = self._detect(detect_security_improvement, self.strong)
        self.assertIsNone(https_clean)

        http_mixed = self._detect(detect_security_improvement, self.legacy)
        self.assertIsNotNone(http_mixed)
        self.assertEqual(http_mixed.score, 90)
        self.assertEqual(http_mixed.business_impact, "Very High")

    def test_website_redesign_fires_on_legacy_platform(self) -> None:
        item = self._detect(detect_website_redesign, self.legacy)
        self.assertIsNotNone(item)
        self.assertGreaterEqual(item.score, 40)

        strong = self._detect(detect_website_redesign, self.strong)
        self.assertIsNone(strong)

    def test_modern_visual_design_reduces_redesign_urgency(self) -> None:
        from dataclasses import replace

        base = legacy_platform_inputs()
        plain = replace(
            base,
            visual_audit={"pages_with_clutter_signal": 0,
                          "pages_with_weak_hierarchy_signal": 0,
                          "pages_with_modern_design_signal": 0},
        )
        modern = replace(
            base,
            visual_audit={"pages_with_clutter_signal": 0,
                          "pages_with_weak_hierarchy_signal": 0,
                          "pages_with_modern_design_signal": 1},
        )
        plain_item = self._detect(detect_website_redesign, plain)
        modern_item = self._detect(detect_website_redesign, modern)
        self.assertIsNotNone(plain_item)
        self.assertIsNotNone(modern_item)
        self.assertLess(modern_item.score, plain_item.score)

    def test_technical_modernization_fires_on_legacy_stack(self) -> None:
        item = self._detect(detect_technical_modernization, self.legacy)
        self.assertIsNotNone(item)
        self.assertGreaterEqual(item.score, 60)

    def test_maintenance_fires_on_legacy_active_site(self) -> None:
        item = self._detect(detect_maintenance_opportunity, self.legacy)
        self.assertIsNotNone(item)
        self.assertGreaterEqual(item.score, 30)

    def test_ecommerce_only_fires_on_ecommerce_signals(self) -> None:
        item = self._detect(detect_ecommerce_optimization, self.ecom)
        self.assertIsNotNone(item)
        self.assertEqual(item.category, "ecommerce_optimization")
        self.assertIn("E-commerce", item.label)

        not_ecom = self._detect(detect_ecommerce_optimization, self.strong)
        self.assertIsNone(not_ecom)

    def test_seo_improvement_fires_on_weak_site(self) -> None:
        weak_item = self._detect(detect_seo_improvement, self.weak)
        self.assertIsNotNone(weak_item)
        self.assertGreaterEqual(weak_item.score, 30)
        self.assertTrue(any("title" in e for e in weak_item.evidence))

        strong_item = self._detect(detect_seo_improvement, self.strong)
        self.assertIsNone(strong_item)

    def test_accessibility_fires_on_missing_alt_and_h1(self) -> None:
        item = self._detect(detect_accessibility_improvement, self.weak)
        self.assertIsNotNone(item)
        self.assertGreaterEqual(item.score, 50)

    def test_mobile_optimization_fires_without_viewport(self) -> None:
        item = self._detect(detect_mobile_optimization, self.legacy)
        self.assertIsNotNone(item)
        self.assertGreaterEqual(item.score, 40)

    def test_local_seo_fires_for_local_business_without_structured_data(self) -> None:
        item = self._detect(detect_local_seo, self.legacy)
        self.assertIsNotNone(item)
        self.assertTrue(any("structured data" in e for e in item.evidence))

    def test_contact_funnel_fires_without_contact_channels(self) -> None:
        weak_item = self._detect(detect_contact_funnel_improvement, self.weak)
        self.assertIsNotNone(weak_item)
        self.assertGreaterEqual(weak_item.score, 30)

        strong_item = self._detect(detect_contact_funnel_improvement, self.strong)
        self.assertIsNone(strong_item)

    def test_conversion_optimization_fires_on_basic_site(self) -> None:
        item = self._detect(detect_conversion_optimization, self.weak)
        self.assertIsNotNone(item)

    def test_hosting_upgrade_fires_on_slow_load_without_cdn(self) -> None:
        item = self._detect(detect_hosting_upgrade, self.legacy)
        self.assertIsNotNone(item)

    def test_performance_fires_on_slow_and_legacy(self) -> None:
        item = self._detect(detect_performance_optimization, self.legacy)
        self.assertIsNotNone(item)
        self.assertGreaterEqual(item.score, 50)

    def test_content_improvement_fires_on_thin_content(self) -> None:
        item = self._detect(detect_content_improvement, self.weak)
        self.assertIsNotNone(item)
        self.assertGreaterEqual(item.score, 30)

    def test_brand_refresh_fires_on_weak_trust(self) -> None:
        item = self._detect(detect_brand_refresh, self.legacy)
        self.assertIsNotNone(item)

    def test_no_website_yields_no_opportunities(self) -> None:
        for detector in (
            detect_accessibility_improvement,
            detect_analytics_setup,
            detect_brand_refresh,
            detect_contact_funnel_improvement,
            detect_content_improvement,
            detect_conversion_optimization,
            detect_ecommerce_optimization,
            detect_hosting_upgrade,
            detect_local_seo,
            detect_maintenance_opportunity,
            detect_mobile_optimization,
            detect_performance_optimization,
            detect_security_improvement,
            detect_seo_improvement,
            detect_technical_modernization,
            detect_website_redesign,
        ):
            item = self._detect(detector, no_website_inputs())
            self.assertIsNone(item, f"{detector.__name__} fired for a no-website lead")

    def test_detectors_never_return_opportunities_below_min_score(self) -> None:
        report = detect_opportunities(weak_site_inputs(), _score_for(weak_site_inputs()))
        for item in report.opportunities:
            self.assertGreaterEqual(item.score, self.config.min_detectable_score)


if __name__ == "__main__":
    unittest.main()
