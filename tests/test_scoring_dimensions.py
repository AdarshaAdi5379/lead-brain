import unittest

from src.scoring import ScoringInputs, score_site_lead
from src.scoring.dimensions import contactability, discovery_quality, seo_health, technical_health
from tests.scoring_fixtures import strong_site_inputs, weak_site_inputs


class TestScoringDimensions(unittest.TestCase):
    def test_contactability_rises_with_channels(self) -> None:
        config = None
        base = contactability(ScoringInputs(website_url="https://x.com"), config)
        self.assertLess(base.score, 50)

        with_phone = contactability(
            ScoringInputs(website_url="https://x.com", extracted={"phone": "512-555-0100"}),
            config,
        )
        self.assertGreater(with_phone.score, base.score)

        full = contactability(
            ScoringInputs(
                website_url="https://x.com",
                extracted={"phone": "512-555-0100", "email": "a@b.com"},
                crawl={"contact_clues": ["a@b.com"], "pages": [{"label": "CONTACT", "url": "/c"}]},
            ),
            config,
        )
        self.assertEqual(full.score, 95)

    def test_discovery_quality_counts_identity_and_location(self) -> None:
        result = discovery_quality(
            ScoringInputs(business_name="Acme", category="plumber", city="Austin", state="TX"),
            None,
        )
        self.assertEqual(result.score, 55)

        bare = discovery_quality(ScoringInputs(), None)
        self.assertEqual(bare.score, 0)

    def test_seo_health_reflects_audit_score_and_penalties(self) -> None:
        good = seo_health(strong_site_inputs(), None)
        self.assertGreaterEqual(good.score, 95)

        weak = seo_health(weak_site_inputs(), None)
        self.assertLess(weak.score, good.score)
        self.assertLess(weak.score, 40)

    def test_seo_health_missing_audit_is_unverifiable_not_crash(self) -> None:
        result = seo_health(ScoringInputs(website_url="https://x.com"), None)
        self.assertEqual(result.score, 25)
        self.assertTrue(any("unverifiable" in r for r in result.reasons))

    def test_technical_health_modern_framework_beats_unknown(self) -> None:
        modern = technical_health(strong_site_inputs(), None)
        self.assertGreater(modern.score, 50)

        bare = technical_health(ScoringInputs(website_url="https://x.com", fetch_ok=True), None)
        self.assertEqual(bare.score, 25)

        broken = technical_health(
            ScoringInputs(website_url="https://x.com", fetch_ok=False), None
        )
        self.assertEqual(broken.score, 0)
        self.assertTrue(any("broken" in r for r in broken.reasons))

    def test_platforms_handled_deterministically(self) -> None:
        for platform in ("wordpress", "shopify", "wix", "custom_react", "unknown"):
            result = technical_health(
                ScoringInputs(
                    website_url="https://x.com",
                    fetch_ok=True,
                    extracted={"platform": platform},
                ),
                None,
            )
            self.assertGreaterEqual(result.score, 0)
            self.assertLessEqual(result.score, 100)
