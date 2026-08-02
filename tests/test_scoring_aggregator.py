import json
import unittest

from src.scoring import ScoringConfig, ScoringInputs, score_site_lead
from src.scoring.aggregator import AVAILABILITY_NOTES
from tests.scoring_fixtures import strong_site_inputs, weak_site_inputs


class TestScoringAggregator(unittest.TestCase):
    def test_strong_site_beats_weak_site(self) -> None:
        strong = score_site_lead(strong_site_inputs())
        weak = score_site_lead(weak_site_inputs())
        self.assertGreater(strong.final_score, weak.final_score)
        self.assertGreaterEqual(strong.final_score, 75)
        self.assertLessEqual(strong.final_score, 100)
        self.assertEqual(strong.priority_label, "Hot")

    def test_score_clamped_to_range(self) -> None:
        inputs = ScoringInputs(website_url="https://x.com", fetch_ok=True)
        config = ScoringConfig(contact_email_points=10_000)
        result = score_site_lead(inputs, config=config)
        self.assertLessEqual(result.final_score, 100)
        for value in result.dimension_scores.values():
            self.assertGreaterEqual(value, 0)
            self.assertLessEqual(value, 100)

    def test_priority_labels_map_correctly(self) -> None:
        # Isolate contactability so the final score equals the dimension score.
        config = ScoringConfig(weights={"contactability": 1.0})
        hot = score_site_lead(
            ScoringInputs(
                website_url="https://x.com",
                extracted={"phone": "1", "email": "a@b.com"},
                crawl={"pages": [{"label": "CONTACT"}]},
            ),
            config=config,
        )
        self.assertEqual(hot.final_score, 85)
        self.assertEqual(hot.priority_label, "Hot")

        warm = score_site_lead(
            ScoringInputs(website_url="https://x.com", extracted={"email": "a@b.com"}),
            config=config,
        )
        self.assertEqual(warm.final_score, 45)
        self.assertEqual(warm.priority_label, "Cold")

        avoid = score_site_lead(ScoringInputs(website_url="https://x.com"), config=config)
        self.assertEqual(avoid.final_score, 15)
        self.assertEqual(avoid.priority_label, "Avoid")

    def test_deterministic_and_json_serializable(self) -> None:
        first = score_site_lead(strong_site_inputs())
        second = score_site_lead(strong_site_inputs())
        self.assertEqual(first.to_dict(), second.to_dict())
        json.dumps(first.to_dict())

    def test_top_reasons_are_stable_and_bounded(self) -> None:
        result = score_site_lead(strong_site_inputs())
        self.assertLessEqual(len(result.top_positive_reasons), 5)
        self.assertLessEqual(len(result.top_negative_reasons), 5)
        for reason in result.top_positive_reasons:
            self.assertNotIn("No ", reason)

    def test_outreach_angle_is_deterministic_template(self) -> None:
        strong = score_site_lead(strong_site_inputs())
        self.assertIsInstance(strong.recommended_outreach_angle, str)
        self.assertTrue(strong.recommended_outreach_angle)

        weak = score_site_lead(weak_site_inputs())
        self.assertIn("opportunity", weak.recommended_outreach_angle.lower())

    def test_availability_notes_are_excluded_from_applicable_dimensions(self) -> None:
        result = score_site_lead(
            ScoringInputs(
                business_name="Acme",
                category="plumber",
                city="Austin",
                state="TX",
                extracted={"phone": "512-555-0100"},
            )
        )
        # No website -> SEO/technical/content/trust are not applicable and
        # their zeros must not dominate the final score.
        self.assertGreaterEqual(result.final_score, 30)
        self.assertIn("No website to assess", AVAILABILITY_NOTES)
        self.assertIn("No website to audit", AVAILABILITY_NOTES)
