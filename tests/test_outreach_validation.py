"""Outreach validation tests: grounding, escaping, fact checks."""

from __future__ import annotations

import unittest

from src.outreach.generator import Fact
from src.outreach.validation import (
    extract_referenced_facts,
    validate_llm_message,
    validate_template_message,
    validate_text_safety,
)

_FACTS = [
    Fact("weak_mobile", "Weak mobile experience", "a weak mobile experience"),
    Fact("missing_meta", "Missing meta descriptions", "missing meta descriptions"),
]

_CONTEXT = {
    "business": {"business_name": "Taco Stand"},
    "contact": {"owner_name": "Joy"},
}


class TestTemplateValidation(unittest.TestCase):
    def test_valid_message(self) -> None:
        ok, issues = validate_template_message(
            "Hi Joy, noticed a weak mobile experience.",
            _CONTEXT,
            facts_used=["Weak mobile experience"],
            facts_available=["Weak mobile experience"],
        )
        self.assertTrue(ok)
        self.assertEqual(issues, [])

    def test_empty_message(self) -> None:
        ok, issues = validate_template_message(
            "   ", _CONTEXT, facts_used=[], facts_available=[]
        )
        self.assertFalse(ok)
        self.assertIn("Message is empty.", issues)

    def test_control_characters(self) -> None:
        ok, issues = validate_template_message(
            "a\x00b", _CONTEXT, facts_used=[], facts_available=[]
        )
        self.assertFalse(ok)
        self.assertIn("Message contains control characters.", issues)

    def test_unrendered_placeholder(self) -> None:
        ok, issues = validate_template_message(
            "Hi {business_name}", _CONTEXT, facts_used=[], facts_available=[]
        )
        self.assertFalse(ok)
        self.assertIn("Message contains an unrendered placeholder.", issues)

    def test_unavailable_fact_rejected(self) -> None:
        ok, issues = validate_template_message(
            "We offer bamboo scaffolding.",
            _CONTEXT,
            facts_used=["Bamboo scaffolding"],
            facts_available=["Weak mobile experience"],
        )
        self.assertFalse(ok)
        self.assertTrue(any("unavailable fact" in issue for issue in issues))

    def test_length_cap(self) -> None:
        ok, issues = validate_template_message(
            "a" * 50, _CONTEXT, facts_used=[], facts_available=[], max_chars=10
        )
        self.assertFalse(ok)
        self.assertIn("Message exceeds the maximum length.", issues)


class TestLlmValidation(unittest.TestCase):
    def test_grounded_draft_passes(self) -> None:
        ok, issues = validate_llm_message(
            "Hi Joy, Taco Stand has a weak mobile experience I can help fix.",
            _CONTEXT,
            _FACTS,
        )
        self.assertTrue(ok)
        self.assertEqual(issues, [])

    def test_empty_draft(self) -> None:
        ok, issues = validate_llm_message("", _CONTEXT, _FACTS)
        self.assertFalse(ok)
        self.assertIn("LLM draft is empty.", issues)

    def test_invented_quoted_name_rejected(self) -> None:
        ok, issues = validate_llm_message(
            'Hi "Bob", Taco Stand has a weak mobile experience.',
            _CONTEXT,
            _FACTS,
        )
        self.assertFalse(ok)
        self.assertTrue(any("unknown name" in issue for issue in issues))

    def test_quoted_real_owner_passes(self) -> None:
        ok, issues = validate_llm_message(
            'Hi "Joy", Taco Stand has a weak mobile experience.',
            _CONTEXT,
            _FACTS,
        )
        self.assertTrue(ok)

    def test_ungrounded_draft_rejected(self) -> None:
        ok, issues = validate_llm_message(
            "Hi there, let us build you a new website tomorrow!",
            _CONTEXT,
            _FACTS,
        )
        self.assertFalse(ok)
        self.assertTrue(any("not grounded" in issue for issue in issues))

    def test_control_characters_rejected(self) -> None:
        ok, issues = validate_llm_message("Hi\x07Taco", _CONTEXT, _FACTS)
        self.assertFalse(ok)
        self.assertTrue(any("control characters" in issue for issue in issues))


class TestFactExtraction(unittest.TestCase):
    def test_extracts_referenced_fact_labels(self) -> None:
        referenced = extract_referenced_facts(
            "Noticed a weak mobile experience on the site.", _FACTS
        )
        self.assertEqual(referenced, ["Weak mobile experience"])

    def test_extracts_nothing_when_unreferenced(self) -> None:
        self.assertEqual(extract_referenced_facts("Nice website.", _FACTS), [])

    def test_empty_message(self) -> None:
        self.assertEqual(extract_referenced_facts("", _FACTS), [])


class TestTextSafety(unittest.TestCase):
    def test_safe_text(self) -> None:
        self.assertTrue(validate_text_safety("Clean text."))

    def test_empty_text(self) -> None:
        self.assertFalse(validate_text_safety(""))
        self.assertFalse(validate_text_safety("  "))

    def test_control_chars(self) -> None:
        self.assertFalse(validate_text_safety("a\x1fb"))

    def test_over_long(self) -> None:
        self.assertFalse(validate_text_safety("a" * 100, max_chars=50))


if __name__ == "__main__":
    unittest.main()
