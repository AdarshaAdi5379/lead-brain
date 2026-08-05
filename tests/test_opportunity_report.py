import unittest

from src.opportunities import detect_opportunities
from src.opportunities.report import (
    CSV_FIELDS,
    csv_fields,
    csv_fields_from_rows,
    to_llm_text,
)
from tests.scoring_fixtures import no_website_inputs, strong_site_inputs, weak_site_inputs
from tests.test_opportunity_detectors import _score_for


class TestOpportunityReport(unittest.TestCase):
    def test_csv_fields_match_spec_columns(self) -> None:
        report = detect_opportunities(weak_site_inputs(), _score_for(weak_site_inputs()))
        fields = csv_fields(report)
        self.assertEqual(set(fields.keys()), set(CSV_FIELDS))
        self.assertEqual(fields["opportunity_score"], report.top_opportunity_score)
        self.assertEqual(fields["opportunity_priority"], report.opportunity_priority)
        self.assertEqual(fields["top_opportunity"], report.top_opportunity)
        self.assertIn(fields["opportunity_count"], (report.opportunity_count, ""))
        self.assertTrue(fields["recommended_services"])

    def test_csv_fields_empty_report(self) -> None:
        report = detect_opportunities(no_website_inputs())
        fields = csv_fields(report)
        self.assertEqual(fields["opportunity_priority"], "Minimal Opportunity")
        self.assertEqual(fields["top_opportunity"], "")

    def test_csv_fields_from_stored_rows(self) -> None:
        report = detect_opportunities(weak_site_inputs(), _score_for(weak_site_inputs()))
        rows = [item.to_dict() for item in report.opportunities]
        for row in rows:
            row["recommended_services_json"] = "|".join(row["recommended_services"])
            row["priority"] = report.opportunity_priority
        summary = csv_fields_from_rows(rows)
        self.assertEqual(summary["opportunity_count"], len(rows))
        self.assertEqual(int(summary["opportunity_score"]), report.top_opportunity_score)
        self.assertEqual(summary["opportunity_priority"], report.opportunity_priority)
        self.assertEqual(summary["top_opportunity"], report.top_opportunity)
        self.assertTrue(summary["recommended_services"])

    def test_csv_fields_from_empty_rows(self) -> None:
        summary = csv_fields_from_rows([])
        self.assertEqual(summary["opportunity_score"], "")
        self.assertEqual(summary["top_opportunity"], "")

    def test_to_llm_text_is_neutral_context(self) -> None:
        report = detect_opportunities(weak_site_inputs(), _score_for(weak_site_inputs()))
        text = to_llm_text(report)
        self.assertIn("deterministic local engine", text)
        self.assertIn(report.top_opportunity, text)
        for item in report.opportunities[:2]:
            self.assertIn(item.label, text)
            self.assertIn(str(item.score), text)

    def test_to_llm_text_empty_report(self) -> None:
        text = to_llm_text(detect_opportunities(no_website_inputs()))
        self.assertIn("no actionable website opportunities", text)
        self.assertNotIn("Contact context", text)

    def test_to_llm_text_includes_contact_context(self) -> None:
        report = detect_opportunities(strong_site_inputs(), _score_for(strong_site_inputs()))
        text = to_llm_text(report)
        self.assertIn("Contact context", text)
        self.assertIn("- Primary contact: acme@example.com", text)
        self.assertIn("- Best contact method: email", text)
        self.assertIn("- Website: https://acme.example.com", text)

    def test_to_llm_text_contact_without_channel_fields(self) -> None:
        report = detect_opportunities(weak_site_inputs(), _score_for(weak_site_inputs()))
        text = to_llm_text(report)
        self.assertIn("- Website: http://weak.example.com", text)
        self.assertNotIn("Primary contact", text)
        self.assertNotIn("Best contact method", text)

    def test_report_dict_includes_contact(self) -> None:
        report = detect_opportunities(strong_site_inputs(), _score_for(strong_site_inputs()))
        self.assertEqual(report.to_dict()["contact"]["email"], "acme@example.com")


if __name__ == "__main__":
    unittest.main()
