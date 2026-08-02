import json
import unittest

from src.opportunities import detect_opportunities
from src.opportunities.base import severity_for_score
from src.opportunities.config import OpportunityConfig, default_config
from tests.opportunity_fixtures import ecommerce_inputs, legacy_platform_inputs
from tests.scoring_fixtures import no_website_inputs, strong_site_inputs, weak_site_inputs
from tests.test_opportunity_detectors import _score_for


class TestOpportunityAggregator(unittest.TestCase):
    def test_severity_bands_match_spec(self) -> None:
        config = default_config()
        cases = [(95, "Critical"), (90, "Critical"), (89, "High"), (70, "High"),
                 (69, "Medium"), (50, "Medium"), (49, "Low"), (30, "Low"),
                 (29, "Ignore"), (0, "Ignore")]
        for score, expected in cases:
            self.assertEqual(severity_for_score(score, config.severity_bands), expected)

    def test_weak_site_yields_multiple_opportunities_sorted(self) -> None:
        report = detect_opportunities(weak_site_inputs(), _score_for(weak_site_inputs()))
        self.assertGreaterEqual(report.opportunity_count, 5)
        scores = [item.score for item in report.opportunities]
        self.assertEqual(scores, sorted(scores, reverse=True))
        self.assertEqual(report.top_opportunity, report.opportunities[0].label)
        self.assertEqual(report.top_opportunity_score, report.opportunities[0].score)
        self.assertIn(report.opportunity_priority, {
            "High Revenue Potential",
            "Medium Revenue Potential",
            "Low Revenue Potential",
            "Minimal Opportunity",
        })

    def test_no_website_yields_empty_report(self) -> None:
        report = detect_opportunities(no_website_inputs())
        self.assertEqual(report.opportunity_count, 0)
        self.assertEqual(report.opportunity_priority, "Minimal Opportunity")
        self.assertEqual(report.top_opportunity, "")
        self.assertEqual(report.top_opportunity_score, 0)

    def test_deterministic_across_runs(self) -> None:
        inputs = weak_site_inputs()
        score = _score_for(inputs)
        first = detect_opportunities(inputs, score)
        second = detect_opportunities(inputs, score)
        self.assertEqual(first.to_dict(), second.to_dict())

    def test_report_is_json_serializable(self) -> None:
        report = detect_opportunities(weak_site_inputs(), _score_for(weak_site_inputs()))
        encoded = json.dumps(report.to_dict())
        self.assertIsInstance(encoded, str)

    def test_ecommerce_priority_derived_from_top_opportunity(self) -> None:
        report = detect_opportunities(ecommerce_inputs(), _score_for(ecommerce_inputs()))
        self.assertGreater(report.opportunity_count, 0)
        self.assertEqual(report.top_opportunity_score, report.opportunities[0].score)

    def test_custom_config_bands_apply(self) -> None:
        config = OpportunityConfig(
            severity_bands=((80, "High"), (50, "Medium"), (30, "Low"))
        )
        report = detect_opportunities(weak_site_inputs(), _score_for(weak_site_inputs()), config)
        for item in report.opportunities:
            self.assertNotEqual(item.severity, "Critical")

    def test_strong_site_still_finds_actionable_opportunities(self) -> None:
        report = detect_opportunities(strong_site_inputs(), _score_for(strong_site_inputs()))
        categories = {item.category for item in report.opportunities}
        self.assertIn("analytics_setup", categories)

    def test_legacy_site_detects_modernization_cluster(self) -> None:
        report = detect_opportunities(legacy_platform_inputs(), _score_for(legacy_platform_inputs()))
        categories = {item.category for item in report.opportunities}
        for expected in (
            "website_redesign",
            "technical_modernization",
            "security_improvement",
            "mobile_optimization",
            "maintenance_opportunity",
        ):
            self.assertIn(expected, categories)


if __name__ == "__main__":
    unittest.main()
