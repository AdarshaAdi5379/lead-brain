import unittest

from src.scoring import ScoringInputs, score_site_lead
from tests.scoring_fixtures import extraction_failed_inputs, no_website_inputs


class TestScoringNoWebsite(unittest.TestCase):
    def test_no_website_but_contactable_ranks_meaningfully(self) -> None:
        result = score_site_lead(no_website_inputs())
        self.assertGreaterEqual(result.final_score, 55)
        self.assertEqual(result.priority_label, "Warm")
        self.assertIn("no website", result.recommended_outreach_angle.lower())

    def test_no_website_phone_only_is_cold_not_avoid(self) -> None:
        result = score_site_lead(
            ScoringInputs(
                business_name="Acme",
                category="plumber",
                city="Austin",
                state="TX",
                extracted={"phone": "512-555-0100"},
            )
        )
        self.assertGreaterEqual(result.final_score, 30)

    def test_no_website_not_unusable(self) -> None:
        result = score_site_lead(no_website_inputs())
        self.assertGreater(result.final_score, 0)

    def test_empty_inputs_are_avoid(self) -> None:
        result = score_site_lead(ScoringInputs())
        self.assertEqual(result.final_score, 0)
        self.assertEqual(result.priority_label, "Avoid")


class TestScoringMissingData(unittest.TestCase):
    def test_extraction_failure_does_not_crash_scoring(self) -> None:
        result = score_site_lead(extraction_failed_inputs())
        self.assertIsNotNone(result.final_score)
        self.assertGreaterEqual(result.final_score, 0)
        self.assertLessEqual(result.final_score, 100)

    def test_missing_fingerprint_is_not_guessed(self) -> None:
        with_fingerprint = score_site_lead(extraction_failed_inputs())
        without = score_site_lead(
            ScoringInputs(
                website_url=extraction_failed_inputs().website_url,
                fetch_ok=False,
                extracted=extraction_failed_inputs().extracted,
            )
        )
        self.assertIsNotNone(without.final_score)

    def test_malformed_inputs_are_tolerated(self) -> None:
        result = score_site_lead(
            ScoringInputs(
                extracted="not-a-dict",
                detections=[{"category": None, "technology_name": None}],
                crawl={"pages": "not-a-list", "contact_clues": None},
                seo_audit={"site_score": "garbage", "pages": None},
                website_url="https://x.com",
                fetch_ok=True,
            )
        )
        self.assertGreaterEqual(result.final_score, 0)
        self.assertLessEqual(result.final_score, 100)

    def test_no_network_requests_involved(self) -> None:
        from unittest.mock import patch

        with patch(
            "socket.socket.connect",
            side_effect=AssertionError("scoring must never open a network connection"),
        ):
            result = score_site_lead(no_website_inputs())
        self.assertGreaterEqual(result.final_score, 0)
