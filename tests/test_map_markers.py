"""Map marker tests: color grouping, payloads, popup safety."""

from __future__ import annotations

import unittest

from src.map.map_data import MapLead
from src.map.map_markers import (
    MARKER_COLORS,
    contact_presence,
    legend_items,
    marker_color,
    marker_payload,
    popup_html,
    website_presence,
)


def _lead(**overrides) -> MapLead:
    base = dict(
        id=1,
        business_name="Taco <b>S</b>tand",
        category="Restaurant",
        city="Austin",
        state="TX",
        platform="WordPress",
        latitude=30.2,
        longitude=-97.7,
        website_url="https://taco.com",
        lead_score=80,
        priority_label="Hot",
        opportunity_score=90,
        has_contact=True,
    )
    base.update(overrides)
    return MapLead(**base)


class TestMarkerStyling(unittest.TestCase):
    def test_score_groups_map_to_colors(self) -> None:
        self.assertEqual(marker_color(80), "red")
        self.assertEqual(marker_color(75), "red")
        self.assertEqual(marker_color(60), "orange")
        self.assertEqual(marker_color(40), "blue")
        self.assertEqual(marker_color(10), "gray")
        self.assertEqual(marker_color(None), "gray")

    def test_legend_lists_all_groups(self) -> None:
        items = dict(legend_items())
        self.assertEqual(items, MARKER_COLORS)
        self.assertEqual(set(items), {"Hot", "Warm", "Cold", "Avoid"})


class TestPresence(unittest.TestCase):
    def test_website_presence_requires_scheme(self) -> None:
        self.assertEqual(website_presence("https://x.com"), "Yes")
        self.assertEqual(website_presence("http://x.com"), "Yes")
        self.assertEqual(website_presence("x.com"), "No")
        self.assertEqual(website_presence(None), "No")

    def test_contact_presence(self) -> None:
        self.assertEqual(contact_presence(True), "Yes")
        self.assertEqual(contact_presence(False), "No")


class TestMarkerPayload(unittest.TestCase):
    def test_full_payload(self) -> None:
        payload = marker_payload(_lead())
        self.assertEqual(payload["business_name"], "Taco <b>S</b>tand")
        self.assertEqual(payload["category"], "Restaurant")
        self.assertEqual(payload["lead_score"], 80)
        self.assertEqual(payload["priority_label"], "Hot")
        self.assertEqual(payload["opportunity_score"], 90)
        self.assertEqual(payload["has_website"], "Yes")
        self.assertEqual(payload["has_contact"], "Yes")

    def test_sparse_lead_defaults(self) -> None:
        payload = marker_payload(
            _lead(
                business_name=None,
                category=None,
                lead_score=None,
                priority_label=None,
                website_url=None,
            )
        )
        self.assertEqual(payload["business_name"], "Lead #1")
        self.assertEqual(payload["category"], "")
        self.assertEqual(payload["priority_label"], "Avoid")
        self.assertEqual(payload["lead_score"], None)
        self.assertEqual(payload["has_website"], "No")


class TestPopup(unittest.TestCase):
    def test_popup_escapes_markup(self) -> None:
        html = popup_html(_lead())
        self.assertIn("&lt;b&gt;", html)
        self.assertNotIn("<b>S</b>", html)

    def test_popup_escapes_injection(self) -> None:
        lead = _lead(business_name='<script>alert("xss")</script>')
        html = popup_html(lead)
        self.assertNotIn("<script>", html)
        self.assertIn("&lt;script&gt;", html)

    def test_popup_includes_key_facts(self) -> None:
        html = popup_html(_lead())
        for needle in (
            "Taco &lt;b&gt;S&lt;/b&gt;tand",
            "Category: Restaurant",
            "Location: Austin, TX",
            "Lead score: 80 (Hot)",
            "Opportunity score: 90",
            "Website:",
            "Contact info: Yes",
        ):
            self.assertIn(needle, html)

    def test_no_website_shown_as_missing(self) -> None:
        html = popup_html(_lead(website_url=None))
        self.assertIn("Website: No website", html)

    def test_unsafe_url_never_linked(self) -> None:
        html = popup_html(_lead(website_url="javascript:alert(1)"))
        self.assertIn("Website: No website", html)
        self.assertNotIn("javascript:", html)
        self.assertNotIn("href=", html)

    def test_http_url_linked_with_rel(self) -> None:
        html = popup_html(_lead(website_url="http://plain.test"))
        self.assertIn('href="http://plain.test"', html)
        self.assertIn("noopener", html)


if __name__ == "__main__":
    unittest.main()