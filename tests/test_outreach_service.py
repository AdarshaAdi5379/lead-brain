"""OutreachService facade tests: real DB, missing leads, never-raises."""

from __future__ import annotations

import unittest

from src.outreach.config import OutreachConfig
from src.outreach.service import OutreachService
from tests.search_fixtures import SearchTestDb


def _service_config() -> OutreachConfig:
    return OutreachConfig(llm_backend="none", enabled=True)


class TestOutreachService(unittest.TestCase):
    def setUp(self) -> None:
        self.db = SearchTestDb()
        self.service = OutreachService(self.db.path, config=_service_config())

    def tearDown(self) -> None:
        self.db.close()

    def _rich_lead(self) -> int:
        lead_id = self.db.add_lead(
            name="Taco Stand", website="https://taco.com", category="Restaurant",
            city="Austin", state="TX", platform="WordPress",
        )
        self.db.add_contact(
            lead_id, owner_name="Joy", email="joy@taco.com",
            phone="512-555-0100", linkedin_url="https://linkedin.com/in/taco",
            contact_form_url="https://taco.com/form",
        )
        self.db.add_detection(lead_id, "WordPress")
        self.db.add_seo(lead_id, 35, "poor")
        self.db.add_visual(lead_id, 40)
        self.db.add_score(lead_id, 62, "Warm")
        self.db.add_opportunity(lead_id, "Redesign", 85)
        self.db.connection.execute(
            "UPDATE visual_audits SET total_pages_audited = 3,"
            " pages_with_weak_mobile_signal = 2, pages_with_modern_design_signal = 0"
            " WHERE lead_id = ?",
            (lead_id,),
        )
        self.db.connection.commit()
        return lead_id

    def test_registry_accessors(self) -> None:
        self.assertEqual(len(self.service.styles()), 6)
        self.assertEqual(len(self.service.lengths()), 3)
        self.assertEqual(self.service.backend_name(), "none")
        self.assertEqual(self.service.contact_method_labels()["email"], "Email")

    def test_contact_methods_available(self) -> None:
        lead_id = self._rich_lead()
        self.assertEqual(
            self.service.contact_methods(lead_id),
            ["auto", "email", "linkedin", "contact_form", "phone"],
        )

    def test_generate_valid_draft(self) -> None:
        lead_id = self._rich_lead()
        draft = self.service.generate(lead_id, style="professional", length="medium")
        self.assertTrue(draft.valid, draft.issues)
        self.assertEqual(draft.mode, "template")
        self.assertEqual(draft.contact_method, "email")
        self.assertEqual(draft.contact_display, "Email (joy@taco.com)")
        self.assertIn("Taco Stand", draft.message)
        self.assertIn("Weak mobile experience", draft.facts_used)
        self.assertIn("Outdated design", draft.facts_used)
        self.assertIn("Contact email available", draft.facts_used)
        self.assertIn("Weak SEO score", draft.facts_available)

    def test_generate_with_explicit_style_length_contact(self) -> None:
        lead_id = self._rich_lead()
        draft = self.service.generate(
            lead_id, style="linkedin_message", length="short", contact_method="phone"
        )
        self.assertEqual(draft.contact_method, "phone")
        self.assertEqual(draft.contact_display, "Phone (512-555-0100)")
        self.assertNotIn("Subject:", draft.message)

    def test_missing_lead_returns_invalid_draft_without_raising(self) -> None:
        draft = self.service.generate(9999, style="professional", length="medium")
        self.assertFalse(draft.valid)
        self.assertEqual(draft.issues, ("missing lead",))
        self.assertIn("No stored intelligence", draft.message)

    def test_missing_lead_contact_methods(self) -> None:
        self.assertEqual(self.service.contact_methods(9999), ["auto"])

    def test_no_contact_lead(self) -> None:
        lead_id = self.db.add_lead(name="Bare Co", website=None)
        draft = self.service.generate(lead_id, style="professional", length="short")
        self.assertTrue(draft.valid, draft.issues)
        self.assertIsNone(draft.contact_method)
        self.assertIn("no active website", draft.message)
        self.assertIn("No direct contact method", " ".join(draft.warnings))


if __name__ == "__main__":
    unittest.main()
