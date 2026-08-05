"""Tests for safety helpers (src/chat/safety.py)."""

from __future__ import annotations

import unittest

from src.chat.safety import fenced_data, redact, sanitize_text, validate_grounded_answer


class SanitizeTests(unittest.TestCase):
    def test_control_characters_stripped(self) -> None:
        raw = "hello\x00\x08\x1f world"
        self.assertEqual(sanitize_text(raw), "hello world")

    def test_runaway_length_capped(self) -> None:
        self.assertEqual(len(sanitize_text("z" * 10_000, max_chars=120)), 120)

    def test_empty_returns_empty(self) -> None:
        self.assertEqual(sanitize_text(""), "")
        self.assertEqual(sanitize_text(None), "")


class RedactTests(unittest.TestCase):
    def test_secret_tokens_redacted(self) -> None:
        self.assertNotIn("sk-abc", redact("key sk-abc123def456ghi789jkl on wire"))
        self.assertNotIn("abcdef", redact("bearer abcdef1234567890abcdef"))

    def test_plain_text_untouched(self) -> None:
        self.assertEqual(redact("hello world"), "hello world")


class FencedDataTests(unittest.TestCase):
    def test_wraps_blocks(self) -> None:
        out = fenced_data(["line one", "line two"])
        self.assertIn("<lead_data>", out)
        self.assertIn("</lead_data>", out)
        self.assertIn("line one", out)

    def test_empty_returns_empty(self) -> None:
        self.assertEqual(fenced_data([]), "")
        self.assertEqual(fenced_data([""]), "")


class ValidateGroundedAnswerTests(unittest.TestCase):
    NAMES = ["Joe's Pizzeria", "Bella Trattoria"]

    def test_valid_reference_passes(self) -> None:
        ok, unknown = validate_grounded_answer(
            "Joe's Pizzeria has weak seo at 35/100.", self.NAMES
        )
        self.assertTrue(ok)
        self.assertEqual(unknown, [])

    def test_digit_reference_is_grounding_evidence(self) -> None:
        ok, _ = validate_grounded_answer("Both leads match; 2 restaurants found.", self.NAMES)
        self.assertTrue(ok)

    def test_hallucinated_unquoted_name_rejected(self) -> None:
        ok, _ = validate_grounded_answer("Moon Cafe on Mars is the best pick.", self.NAMES)
        self.assertFalse(ok)

    def test_hallucinated_quoted_name_rejected(self) -> None:
        ok, unknown = validate_grounded_answer(
            '"Moon Cafe" is the best pick for redesign.', self.NAMES
        )
        self.assertFalse(ok)
        self.assertEqual(unknown, ["Moon Cafe"])

    def test_known_quoted_name_ok(self) -> None:
        ok, _ = validate_grounded_answer(
            '"Bella Trattoria" scored well in seo.', self.NAMES
        )
        self.assertTrue(ok)

    def test_empty_answer_rejected(self) -> None:
        self.assertFalse(validate_grounded_answer("", self.NAMES)[0])
        self.assertFalse(validate_grounded_answer("   ", self.NAMES)[0])


if __name__ == "__main__":
    unittest.main()