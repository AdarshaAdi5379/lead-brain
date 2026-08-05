"""Outreach generator tests: facts, contact selection, template vs LLM modes."""

from __future__ import annotations

import unittest

from src.outreach.config import OutreachConfig
from src.outreach.generator import (
    available_contact_methods,
    generate_outreach,
    select_contact_method,
    signal_facts,
)
from tests.chat_fixtures import FakeLLMBackend


def _rich_context() -> dict:
    return {
        "business": {"business_name": "Taco Stand", "category": "Restaurant"},
        "location": {"city": "Austin", "state": "TX"},
        "contact": {
            "owner_name": "Joy",
            "email": "joy@taco.com",
            "phone": "512-555-0100",
            "website_url": "https://taco.com",
        },
        "social_presence": {"linkedin": "https://linkedin.com/in/taco"},
        "technology": {"platform": "WordPress"},
        "seo": {"site_score": 55, "overall_health": "poor"},
        "visual": {"visual_score": 40},
        "top_seo_issues": ["Missing meta descriptions", "Thin content on some pages"],
        "top_visual_issues": ["Weak mobile experience"],
        "top_opportunities": [
            {"label": "Website redesign", "score": 85, "recommended_services": ["Redesign"]}
        ],
        "opportunity_summary": {"count": 1, "recommended_services": ["Redesign"]},
        "business_summary": "Taco Stand, a Restaurant in Austin, TX",
        "reachability": {
            "email": True,
            "linkedin": True,
            "facebook": False,
            "whatsapp": False,
            "contact_form": False,
            "phone": True,
        },
    }


def _bare_context() -> dict:
    return {
        "business": {"business_name": "Bare Co"},
        "location": {},
        "contact": {},
        "social_presence": {},
        "technology": {},
        "seo": {},
        "visual": {},
        "top_seo_issues": [],
        "top_visual_issues": [],
        "top_opportunities": [],
        "opportunity_summary": {},
        "business_summary": "",
        "reachability": {},
    }


def _config(**overrides) -> OutreachConfig:
    base = {"llm_backend": "none", "enabled": True}
    base.update(overrides)
    return OutreachConfig(**base)


class TestSignalFacts(unittest.TestCase):
    def test_no_website_lead_only_reports_that(self) -> None:
        facts = signal_facts(_bare_context())
        self.assertEqual([fact.key for fact in facts], ["no_website"])
        self.assertEqual(facts[0].label, "No website found")

    def test_rich_lead_facts(self) -> None:
        facts = signal_facts(_rich_context())
        keys = [fact.key for fact in facts]
        self.assertIn("weak_mobile", keys)
        self.assertIn("missing_meta", keys)
        self.assertIn("thin_content", keys)
        self.assertIn("platform_wordpress", keys)
        self.assertIn("modern_weak_local_seo", keys)
        self.assertIn("no_contact_form", keys)
        self.assertNotIn("weak_seo", keys)

    def test_facts_are_deduplicated(self) -> None:
        context = _rich_context()
        context["top_seo_issues"] = ["Missing meta descriptions", "Missing meta descriptions"]
        keys = [fact.key for fact in signal_facts(context)]
        self.assertEqual(keys.count("missing_meta"), 1)

    def test_unknown_platform_skips_platform_facts(self) -> None:
        context = _rich_context()
        context["technology"]["platform"] = "unknown"
        context["seo"]["site_score"] = 35
        keys = [fact.key for fact in signal_facts(context)]
        self.assertNotIn("platform_unknown", keys)
        self.assertIn("weak_seo", keys)

    def test_contact_form_present_omits_fact(self) -> None:
        context = _rich_context()
        context["contact"]["contact_form_url"] = "https://taco.com/form"
        keys = [fact.key for fact in signal_facts(context)]
        self.assertNotIn("no_contact_form", keys)

    def test_social_presence_present_omits_fact(self) -> None:
        context = _rich_context()
        keys = [fact.key for fact in signal_facts(context)]
        self.assertNotIn("no_social", keys)


class TestContactSelection(unittest.TestCase):
    def test_priority_order(self) -> None:
        self.assertEqual(
            available_contact_methods(_rich_context()),
            ["email", "linkedin", "phone"],
        )

    def test_auto_selects_first_priority(self) -> None:
        method, target = select_contact_method(_rich_context(), "auto")
        self.assertEqual((method, target), ("email", "joy@taco.com"))

    def test_preferred_method_respected(self) -> None:
        method, target = select_contact_method(_rich_context(), "linkedin")
        self.assertEqual((method, target), ("linkedin", "https://linkedin.com/in/taco"))

    def test_preferred_unavailable_falls_back(self) -> None:
        method, _target = select_contact_method(_rich_context(), "whatsapp")
        self.assertEqual(method, "email")

    def test_no_channels_returns_none(self) -> None:
        self.assertIsNone(select_contact_method(_bare_context(), "auto"))
        self.assertEqual(available_contact_methods(_bare_context()), [])

    def test_reachability_fallback_from_contact_fields(self) -> None:
        context = _bare_context()
        context["reachability"] = {}
        context["contact"] = {"email": "joy@taco.com"}
        method, target = select_contact_method(context, "auto")
        self.assertEqual((method, target), ("email", "joy@taco.com"))


class TestGenerateTemplateMode(unittest.TestCase):
    def test_all_styles_render_valid_messages(self) -> None:
        config = _config()
        for style in ("professional", "friendly", "consultative", "short_intro", "follow_up", "linkedin_message"):
            with self.subTest(style=style):
                draft = generate_outreach(_rich_context(), style=style, length="medium", backend=None, config=config)
                self.assertTrue(draft.message.strip())
                self.assertEqual(draft.mode, "template")
                self.assertTrue(draft.valid, (draft.issues, draft.message))

    def test_all_lengths_render_valid_messages(self) -> None:
        config = _config()
        for length in ("short", "medium", "long"):
            with self.subTest(length=length):
                draft = generate_outreach(_rich_context(), style="professional", length=length, backend=None, config=config)
                self.assertTrue(draft.valid, draft.issues)
                self.assertIn("Taco Stand", draft.message)

    def test_facts_used_and_available(self) -> None:
        draft = generate_outreach(_rich_context(), style="professional", length="medium", backend=None, config=_config())
        self.assertIn("Weak mobile experience", draft.facts_used)
        self.assertIn("Contact email available", draft.facts_used)
        self.assertIn("Thin content on some pages", draft.facts_available)
        self.assertNotIn("Thin content on some pages", draft.facts_used)

    def test_contact_selection_and_display(self) -> None:
        draft = generate_outreach(_rich_context(), style="professional", length="short", backend=None, config=_config())
        self.assertEqual(draft.contact_method, "email")
        self.assertEqual(draft.contact_target, "joy@taco.com")
        self.assertEqual(draft.contact_display, "Email (joy@taco.com)")

    def test_no_contact_lead(self) -> None:
        draft = generate_outreach(_bare_context(), style="professional", length="short", backend=None, config=_config())
        self.assertIsNone(draft.contact_method)
        self.assertIsNone(draft.contact_display)
        self.assertIn("No direct contact method", " ".join(draft.warnings))
        self.assertIn("no active website", draft.message)

    def test_style_and_length_fallbacks(self) -> None:
        draft = generate_outreach(_rich_context(), style="not_a_style", length="not_a_length", backend=None, config=_config())
        self.assertEqual(draft.style, "professional")
        self.assertEqual(draft.length, "medium")

    def test_disabled_config_uses_template(self) -> None:
        backend = FakeLLMBackend("Hi Joy, Taco Stand has a weak mobile experience.")
        draft = generate_outreach(_rich_context(), style="professional", length="short", backend=backend, config=_config(enabled=False))
        self.assertEqual(draft.mode, "template")
        self.assertEqual(backend.calls, [])


class TestGenerateLlmMode(unittest.TestCase):
    def test_grounded_llm_draft_is_used(self) -> None:
        backend = FakeLLMBackend("Hi Joy, I reviewed Taco Stand and noticed a weak mobile experience. Happy to help.")
        draft = generate_outreach(_rich_context(), style="friendly", length="short", backend=backend, config=_config(llm_backend="auto"))
        self.assertEqual(draft.mode, "llm")
        self.assertEqual(draft.message, "Hi Joy, I reviewed Taco Stand and noticed a weak mobile experience. Happy to help.")
        self.assertTrue(draft.valid)
        self.assertEqual(len(backend.calls), 1)
        system_prompt, user_prompt = backend.calls[0]
        self.assertIn("Hard rules", system_prompt)
        self.assertIn("Never invent", system_prompt)
        self.assertIn("<lead_data>", user_prompt)
        self.assertIn("Contact method: Email (joy@taco.com)", user_prompt)
        self.assertIn("Weak mobile experience", draft.facts_used)

    def test_ungrounded_llm_draft_falls_back_to_template(self) -> None:
        backend = FakeLLMBackend("Hi there, let us build you a brand new site tomorrow!")
        draft = generate_outreach(_rich_context(), style="friendly", length="short", backend=backend, config=_config(llm_backend="auto"))
        self.assertEqual(draft.mode, "template")
        self.assertTrue(draft.valid)
        self.assertIn("LLM draft failed grounding checks; using a template.", draft.warnings)

    def test_invented_name_llm_draft_falls_back(self) -> None:
        backend = FakeLLMBackend('Hi "Bob", Taco Stand has a weak mobile experience.')
        draft = generate_outreach(_rich_context(), style="friendly", length="short", backend=backend, config=_config(llm_backend="auto"))
        self.assertEqual(draft.mode, "template")
        self.assertIn("LLM draft failed grounding checks; using a template.", draft.warnings)

    def test_no_response_falls_back(self) -> None:
        backend = FakeLLMBackend(None)
        draft = generate_outreach(_rich_context(), style="friendly", length="short", backend=backend, config=_config(llm_backend="auto"))
        self.assertEqual(draft.mode, "template")
        self.assertIn("No local LLM response; using a template draft.", draft.warnings)

    def test_unavailable_backend_uses_template(self) -> None:
        backend = FakeLLMBackend("Hi Joy, Taco Stand is great.", available=False)
        draft = generate_outreach(_rich_context(), style="friendly", length="short", backend=backend, config=_config(llm_backend="auto"))
        self.assertEqual(draft.mode, "template")

    def test_never_raises_on_junk_context(self) -> None:
        draft = generate_outreach({}, style="professional", length="medium", backend=None, config=_config())
        self.assertTrue(draft.valid)
        self.assertTrue(draft.message.strip())


if __name__ == "__main__":
    unittest.main()
