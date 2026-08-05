"""Outreach renderer tests: composition, lengths, sanitization, caps."""

from __future__ import annotations

import unittest

from src.outreach.generator import Fact
from src.outreach.renderer import compose_message


def _context() -> dict:
    return {
        "business": {"business_name": "Taco Stand", "category": "Restaurant"},
        "location": {"city": "Austin", "state": "TX"},
        "contact": {"owner_name": "Joy", "website_url": "https://taco.com"},
        "top_opportunities": [{"label": "Website redesign", "recommended_services": ["Redesign"]}],
        "opportunity_summary": {"recommended_services": ["Redesign"]},
        "business_summary": "Taco Stand, a Restaurant in Austin, TX",
    }


_FACTS = [
    Fact("weak_mobile", "Weak mobile experience", "a weak mobile experience"),
    Fact("missing_meta", "Missing meta descriptions", "missing meta descriptions"),
]


class TestRenderer(unittest.TestCase):
    def test_medium_professional_message(self) -> None:
        message = compose_message(_context(), style="professional", length="medium", facts=_FACTS)
        self.assertTrue(message.startswith("Subject: Website improvement plan for Taco Stand"))
        for needle in (
            "Hi Joy,",
            "I took a close look at the Taco Stand website in Austin, TX",
            "The clearest opportunity here is Website redesign.",
            "Would you be open to a quick 10-minute call",
            "Best regards,",
        ):
            self.assertIn(needle, message)
        self.assertNotIn("For context,", message)

    def test_short_omits_opportunity_and_offer(self) -> None:
        message = compose_message(_context(), style="professional", length="short", facts=_FACTS)
        self.assertNotIn("clearest opportunity", message)
        self.assertNotIn("no long contracts", message)
        self.assertIn("10-minute call", message)

    def test_long_adds_business_context(self) -> None:
        message = compose_message(_context(), style="professional", length="long", facts=_FACTS)
        self.assertIn("For context, Taco Stand, a Restaurant in Austin, TX.", message)

    def test_linkedin_message_has_no_subject_or_closing(self) -> None:
        message = compose_message(_context(), style="linkedin_message", length="medium", facts=_FACTS)
        self.assertNotIn("Subject:", message)
        self.assertNotIn("Best regards", message)
        self.assertIn("Open to a quick chat?", message)

    def test_control_characters_are_stripped(self) -> None:
        context = _context()
        context["business"]["business_name"] = "Taco\x01Stand"
        message = compose_message(context, style="professional", length="short", facts=_FACTS)
        self.assertNotIn("\x01", message)
        self.assertIn("TacoStand", message)

    def test_no_triple_blank_lines(self) -> None:
        message = compose_message(_context(), style="professional", length="long", facts=_FACTS)
        self.assertNotIn("\n\n\n", message)

    def test_length_cap(self) -> None:
        message = compose_message(_context(), style="professional", length="long", facts=_FACTS, max_chars=50)
        self.assertLessEqual(len(message), 50)

    def test_no_website_message_is_honest(self) -> None:
        context = _context()
        context["contact"] = {}
        context["top_opportunities"] = []
        context["opportunity_summary"] = {}
        message = compose_message(context, style="professional", length="medium", facts=[])
        self.assertIn("no active website for Taco Stand", message)
        self.assertNotIn("I took a close look at the Taco Stand website", message)
        self.assertIn("getting Taco Stand online with a working website", message)


if __name__ == "__main__":
    unittest.main()
