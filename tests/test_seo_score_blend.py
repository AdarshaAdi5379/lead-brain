import unittest

from src.scoring import score_lead


def _basic_extracted() -> dict:
    return {
        "website_url": "https://example.com/",
        "platform": "unknown",
        "complexity": "unknown",
        "load_speed": "unknown",
        "phone": None,
        "email": None,
    }


class TestSeoScoreBlend(unittest.TestCase):
    def test_default_call_unchanged(self) -> None:
        without_seo = score_lead(_basic_extracted())
        with_seo_none = score_lead(_basic_extracted(), site_seo_score=None)
        self.assertEqual(without_seo.score, with_seo_none.score)
        self.assertEqual(without_seo.reasons, with_seo_none.reasons)

    def test_high_seo_score_lifts_lead_score(self) -> None:
        base = score_lead(_basic_extracted())
        blended = score_lead(_basic_extracted(), site_seo_score=100)
        self.assertGreater(blended.score, base.score)

    def test_low_seo_score_lowers_lead_score(self) -> None:
        base = score_lead(_basic_extracted())
        blended = score_lead(_basic_extracted(), site_seo_score=0)
        self.assertLess(blended.score, base.score)

    def test_blend_math_with_default_weight(self) -> None:
        # Base score is 80 (50 baseline + 30 for missing phone/email).
        result = score_lead(_basic_extracted(), site_seo_score=100)
        self.assertEqual(result.score, 83)  # 0.85*80 + 0.15*100, rounded
        self.assertIn("SEO site score (100/100)", result.reasons)

    def test_custom_blend_weight(self) -> None:
        result = score_lead(_basic_extracted(), site_seo_score=100, seo_blend_weight=0.5)
        self.assertEqual(result.score, 90)  # 0.5*80 + 0.5*100

    def test_invalid_seo_score_ignored(self) -> None:
        base = score_lead(_basic_extracted())
        blended = score_lead(_basic_extracted(), site_seo_score="not-a-number")
        self.assertEqual(base.score, blended.score)
        self.assertNotIn("SEO site score", " ".join(blended.reasons))

    def test_no_website_branch_ignores_seo(self) -> None:
        extracted = {
            "website_url": None,
            "business_name": "Acme",
        }
        base = score_lead(extracted)
        blended = score_lead(extracted, site_seo_score=0)
        self.assertEqual(base.score, blended.score)

    def test_seo_score_clamped_to_range(self) -> None:
        result = score_lead(_basic_extracted(), site_seo_score=999)
        self.assertEqual(result.score, 83)


if __name__ == "__main__":
    unittest.main()
