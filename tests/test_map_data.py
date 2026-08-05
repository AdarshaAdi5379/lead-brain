"""Map data tests: coordinate loading, invalid skip, score joins, options."""

from __future__ import annotations

import unittest

from src.map.map_data import load_map_leads, option_values
from tests.search_fixtures import SearchTestDb


def _set_coords(db: SearchTestDb, lead_id: int, lat, lon) -> None:
    db.connection.execute(
        "UPDATE leads SET latitude = ?, longitude = ? WHERE id = ?",
        (lat, lon, lead_id),
    )
    db.connection.commit()


class TestMapData(unittest.TestCase):
    def setUp(self) -> None:
        self.db = SearchTestDb()

    def tearDown(self) -> None:
        self.db.close()

    def test_loads_leads_with_valid_coordinates(self) -> None:
        lead_id = self.db.add_lead(name="Taco Stand", city="Austin", state="TX", platform="WordPress")
        _set_coords(self.db, lead_id, 30.2, -97.7)
        leads = load_map_leads(self.db.connection)
        self.assertEqual(len(leads), 1)
        lead = leads[0]
        self.assertEqual(lead.id, lead_id)
        self.assertEqual(lead.business_name, "Taco Stand")
        self.assertEqual(lead.city, "Austin")
        self.assertEqual(lead.state, "TX")
        self.assertEqual(lead.platform, "WordPress")
        self.assertEqual((lead.latitude, lead.longitude), (30.2, -97.7))

    def test_leads_without_coordinates_are_excluded(self) -> None:
        self.db.add_lead(name="No Coords", city="Austin")
        with_coords = self.db.add_lead(name="Has Coords", city="Dallas")
        _set_coords(self.db, with_coords, 32.7, -96.8)
        leads = load_map_leads(self.db.connection)
        self.assertEqual([lead.id for lead in leads], [with_coords])

    def test_invalid_coordinates_are_skipped_safely(self) -> None:
        bad = self.db.add_lead(name="Bad Coords")
        good = self.db.add_lead(name="Good Coords")
        _set_coords(self.db, bad, 99.0, -97.7)
        _set_coords(self.db, good, 30.2, -97.7)
        leads = load_map_leads(self.db.connection)
        self.assertEqual([lead.id for lead in leads], [good])

    def test_non_numeric_coordinates_are_skipped(self) -> None:
        lead_id = self.db.add_lead(name="String Coords")
        _set_coords(self.db, lead_id, "north", "-west")
        self.assertEqual(load_map_leads(self.db.connection), [])

    def test_scores_and_opportunity_joined(self) -> None:
        lead_id = self.db.add_lead(name="Scored", website="https://x.com")
        _set_coords(self.db, lead_id, 30.2, -97.7)
        self.db.add_score(lead_id, 78, "Hot")
        self.db.add_opportunity(lead_id, "Redesign", 85)
        self.db.add_opportunity(lead_id, "SEO", 92)
        lead = load_map_leads(self.db.connection)[0]
        self.assertEqual(lead.lead_score, 78)
        self.assertEqual(lead.priority_label, "Hot")
        self.assertEqual(lead.opportunity_score, 92)

    def test_contact_presence_flag(self) -> None:
        with_contact = self.db.add_lead(name="Contacted")
        _set_coords(self.db, with_contact, 30.2, -97.7)
        self.db.add_contact(with_contact, email="a@b.com", phone="111")
        without = self.db.add_lead(name="Lonely")
        _set_coords(self.db, without, 31.0, -98.0)
        leads = {lead.id: lead for lead in load_map_leads(self.db.connection)}
        self.assertTrue(leads[with_contact].has_contact)
        self.assertFalse(leads[without].has_contact)

    def test_website_url_and_missing_score(self) -> None:
        lead_id = self.db.add_lead(name="Bare", website="https://bare.com")
        _set_coords(self.db, lead_id, 30.2, -97.7)
        lead = load_map_leads(self.db.connection)[0]
        self.assertEqual(lead.website_url, "https://bare.com")
        self.assertIsNone(lead.lead_score)
        self.assertEqual(lead.opportunity_score, 0)

    def test_option_values(self) -> None:
        for name, city, state, category, platform in (
            ("A", "Austin", "TX", "Cafe", "WordPress"),
            ("B", "Dallas", "TX", "Cafe", "Wix"),
            ("C", "Austin", "TX", "Barber", "WordPress"),
        ):
            lead_id = self.db.add_lead(
                name=name, city=city, state=state, category=category, platform=platform
            )
            _set_coords(self.db, lead_id, 30.0, -97.0)
        values = option_values(load_map_leads(self.db.connection))
        self.assertEqual(values["cities"], ["Austin", "Dallas"])
        self.assertEqual(values["states"], ["TX"])
        self.assertEqual(values["categories"], ["Barber", "Cafe"])
        self.assertEqual(values["platforms"], ["Wix", "WordPress"])
        self.assertEqual(option_values([]), {"categories": [], "cities": [], "states": [], "platforms": []})


if __name__ == "__main__":
    unittest.main()