"""Outreach template tests: style registry, sections, no-website variants."""

from __future__ import annotations

import unittest

from src.outreach import templates
from src.outreach.generator import Fact


def _context(website: bool = True) -> dict:
    return {
        "business": {"business_name": "Taco Stand", "category": "Restaurant"},
        "location": {"city": "Austin", "state": "TX"},
        "contact": (
            {"owner_name": "Joy", "website_url": "https://taco.com"}
            if website
            else {}
        ),
        "top_opportunities": [{"label": "Website redesign", "recommended_services": ["Redesign"]}],
        "opportunity_summary": {"recommended_services": ["Redesign"]},
        "business_summary": "Taco Stand, a Restaurant in Austin, TX",
    }


_FACTS = [
    Fact("weak_mobile", "Weak mobile experience", "a weak mobile experience"),
    Fact("missing_meta", "Missing meta descriptions", "missing meta descriptions"),
    Fact("weak_seo", "Weak SEO", "weak search visibility"),
]


class TestTemplates(unittest.TestCase):
    def test_style_and_length_registry(self) -> None:
        self.assertEqual(
            list(templates.styles()),
            ["professional", "friendly", "consultative", "short_intro", "follow_up", "linkedin_message"],
        )
        self.assertEqual(list(templates.lengths()), ["short", "medium", "long"])

    def test_section_order_per_length(self) -> None:
        self.assertEqual(
            list(templates.section_names("professional", "short")),
            ["greeting", "observation", "insight", "cta", "closing"],
        )
        self.assertEqual(len(templates.section_names("professional", "medium")), 7)
        self.assertEqual(len(templates.section_names("professional", "long")), 8)
        self.assertIn("business_context", templates.section_names("professional", "long"))
        self.assertEqual(templates.facts_per_length("short"), 1)
        self.assertEqual(templates.facts_per_length("medium"), 2)
        self.assertEqual(templates.facts_per_length("long"), 3)

    def test_subject_support(self) -> None:
        self.assertTrue(templates.has_subject("professional"))
        self.assertTrue(templates.has_subject("follow_up"))
        self.assertFalse(templates.has_subject("linkedin_message"))

    def test_fact_phrase_joining(self) -> None:
        self.assertEqual(templates.fact_phrase([_FACTS[0]]), "a weak mobile experience")
        self.assertEqual(
            templates.fact_phrase(_FACTS[:2]),
            "a weak mobile experience and missing meta descriptions",
        )
        self.assertEqual(
            templates.fact_phrase(_FACTS),
            "a weak mobile experience, missing meta descriptions and weak search visibility",
        )
        self.assertIn("opportunities", templates.fact_phrase([]))

    def test_greeting_uses_owner_name(self) -> None:
        greeting = templates.render_section("greeting", _context(), "professional", [])
        self.assertEqual(greeting, "Hi Joy,")

    def test_all_styles_render_observation_and_insight(self) -> None:
        for style in templates.STYLES:
            with self.subTest(style=style):
                observation = templates.render_section("observation", _context(), style, _FACTS)
                insight = templates.render_section("insight", _context(), style, _FACTS)
                self.assertTrue(observation.strip())
                self.assertTrue(insight.strip())
                self.assertIn("Taco Stand", observation)
                self.assertNotIn("{", observation)
                self.assertNotIn("{", insight)

    def test_no_website_observation_is_honest(self) -> None:
        context = _context(website=False)
        observation = templates.render_section("observation", context, "professional", _FACTS)
        insight = templates.render_section("insight", context, "professional", _FACTS)
        self.assertEqual(
            observation, "I came across Taco Stand in Austin, TX and wanted to reach out."
        )
        self.assertEqual(
            insight, "It looks like there is no active website for Taco Stand yet."
        )
        self.assertNotIn("website", observation)

    def test_no_website_opportunity_text(self) -> None:
        context = _context(website=False)
        opportunity = templates.render_section("opportunity", context, "professional", _FACTS)
        self.assertEqual(
            opportunity,
            "The clearest opportunity here is getting Taco Stand online with a working website.",
        )

    def test_subject_render(self) -> None:
        subject = templates.render_subject("professional", _context())
        self.assertEqual(subject, "Website improvement plan for Taco Stand")
        self.assertEqual(templates.render_subject("linkedin_message", _context()), "")

    def test_empty_sections_are_omitted(self) -> None:
        self.assertEqual(
            templates.render_section("opportunity", _context(), "short_intro", _FACTS), ""
        )
        self.assertEqual(
            templates.render_section("closing", _context(), "linkedin_message", _FACTS), ""
        )


if __name__ == "__main__":
    unittest.main()
