"""Contact display helper tests: grouping, NULL omission, determinism."""

from __future__ import annotations

import unittest

from src.contact.display import CONTACT_FIELDS, group_contact_facts, lead_contact_dict


class TestLeadContactDict(unittest.TestCase):
    def test_drops_empty_and_none(self) -> None:
        facts = lead_contact_dict(
            {
                "owner_name": "Joy",
                "address": "",
                "postal_code": None,
                "country": "US",
                "phone": "  ",
                "service_areas": [],
            }
        )
        self.assertEqual(facts, {"owner_name": "Joy", "country": "US"})

    def test_whitelist_fields_only(self) -> None:
        facts = lead_contact_dict({"owner_name": "Joy", "unexpected": "x"})
        self.assertEqual(set(facts), {"owner_name"})


class TestGroupContactFacts(unittest.TestCase):
    def test_includes_only_present_facts(self) -> None:
        rows = group_contact_facts(
            {
                "owner_name": "Joy",
                "phone": "512-555-0100",
                "email": "joy@example.com",
                "postal_code": "75039",
                "whatsapp_url": "https://wa.me/1555",
                "opening_hours": "Mon-Fri 9am-5pm",
            }
        )
        labels = [label for _, label, _ in rows]
        self.assertIn("Owner", labels)
        self.assertIn("Phone", labels)
        self.assertIn("Email", labels)
        self.assertIn("Postal code", labels)
        self.assertIn("WhatsApp", labels)
        self.assertIn("Opening hours", labels)
        self.assertNotIn("Facebook", labels)
        self.assertNotIn("Address", labels)

    def test_grouped_order_is_stable(self) -> None:
        flat = {
            "email": "a@b.com",
            "country": "US",
            "owner_name": "Joy",
            "opening_hours": "Mon-Fri",
            "address": "100 Main St",
            "phone": "512",
            "whatsapp_url": "https://wa.me/1",
            "facebook_url": "https://fb.com/x",
        }
        rows = group_contact_facts(flat)
        groups = [group for group, _, _ in rows]
        self.assertEqual(groups, sorted(groups, key=groups.index))
        self.assertEqual(groups[0], "Business")
        self.assertIn("Contact", groups)
        self.assertIn("Location", groups)
        self.assertIn("Opening hours", groups)

    def test_service_areas_renders_joined(self) -> None:
        rows = group_contact_facts({"service_areas": ["Austin", "Round Rock"]})
        service = [(label, value) for group, label, value in rows]
        self.assertIn(("Service areas", "Austin, Round Rock"), service)

    def test_service_areas_empty_list_is_omitted(self) -> None:
        rows = group_contact_facts({"service_areas": []})
        self.assertEqual(rows, [])

    def test_empty_input_returns_empty(self) -> None:
        self.assertEqual(group_contact_facts({}), [])
        self.assertEqual(group_contact_facts({"owner_name": None}), [])

    def test_urls_keep_their_values(self) -> None:
        rows = dict(
            (label, value)
            for group, label, value in group_contact_facts(
                {"website_url": "https://x.com", "contact_form_url": "https://x.com/cf"}
            )
        )
        self.assertEqual(rows["Website"], "https://x.com")
        self.assertEqual(rows["Contact form"], "https://x.com/cf")


if __name__ == "__main__":
    unittest.main()