import json
import unittest

from src.scoring import score_site_lead
from src.scoring.report import csv_fields, csv_fields_from_row, to_llm_text
from tests.scoring_fixtures import strong_site_inputs, weak_site_inputs


class TestScoringReport(unittest.TestCase):
    def test_to_dict_is_json_serializable(self) -> None:
        score = score_site_lead(strong_site_inputs())
        payload = score.to_dict()
        json.dumps(payload)
        self.assertIn("final_score", payload)
        self.assertIn("priority_label", payload)
        self.assertIn("dimension_scores", payload)
        self.assertIn("dimension_reasons", payload)
        self.assertIn("recommended_outreach_angle", payload)

    def test_csv_fields_shape(self) -> None:
        score = score_site_lead(strong_site_inputs())
        fields = csv_fields(score)
        self.assertEqual(fields["final_score"], score.final_score)
        self.assertEqual(fields["priority_label"], score.priority_label)
        self.assertEqual(
            fields["contactability_score"], score.dimension_scores["contactability"]
        )
        self.assertIn("top_positive_reasons", fields)
        self.assertIn("recommended_outreach_angle", fields)

    def test_csv_fields_from_row_matches_row_semantics(self) -> None:
        score = score_site_lead(weak_site_inputs())
        row = {
            "final_score": score.final_score,
            "priority_label": score.priority_label,
            "discovery_quality_score": score.dimension_scores["discovery_quality"],
            "contactability_score": score.dimension_scores["contactability"],
            "technical_health_score": score.dimension_scores["technical_health"],
            "seo_health_score": score.dimension_scores["seo_health"],
            "content_strength_score": score.dimension_scores["content_strength"],
            "trust_professionalism_score": score.dimension_scores["trust_professionalism"],
            "outreach_potential_score": score.dimension_scores["outreach_potential"],
            "top_positive_reasons_json": json.dumps(score.top_positive_reasons),
            "top_negative_reasons_json": json.dumps(score.top_negative_reasons),
            "recommended_outreach_angle": score.recommended_outreach_angle,
        }
        fields = csv_fields_from_row(row)
        self.assertEqual(fields["final_score"], score.final_score)
        self.assertEqual(fields["priority_label"], score.priority_label)
        self.assertIn(score.top_positive_reasons[0], fields["top_positive_reasons"])
        self.assertEqual(fields["recommended_outreach_angle"], score.recommended_outreach_angle)

    def test_to_llm_text_marks_neutral_context(self) -> None:
        score = score_site_lead(strong_site_inputs())
        text = to_llm_text(score)
        self.assertTrue(text.endswith("\n"))
        self.assertIn("deterministic local model", text)
        self.assertIn(f"{score.final_score}/100", text)
        self.assertIn("Recommended outreach angle", text)
