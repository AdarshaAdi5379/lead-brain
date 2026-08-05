"""MapService tests: DB loading, filter integration, graceful rendering."""

from __future__ import annotations

import unittest

from src.map.map_render import folium_available
from src.map.map_service import MapService
from tests.map_fixtures import map_lead, map_leads
from tests.search_fixtures import SearchTestDb


class TestMapService(unittest.TestCase):
    def setUp(self) -> None:
        self.db = SearchTestDb()
        self.service = MapService(self.db.path)

    def tearDown(self) -> None:
        self.db.close()

    def _add_geolocated(self, name: str, lat: float, lon: float, score: int = 60, priority: str = "Warm") -> int:
        lead_id = self.db.add_lead(name=name, city="Austin", state="TX")
        self.db.connection.execute(
            "UPDATE leads SET latitude = ?, longitude = ? WHERE id = ?",
            (lat, lon, lead_id),
        )
        self.db.connection.commit()
        self.db.add_score(lead_id, score, priority)
        return lead_id

    def test_load_leads_only_geolocated(self) -> None:
        self.db.add_lead(name="No Coords")
        with_coords = self._add_geolocated("With Coords", 30.2, -97.7)
        leads = self.service.load_leads()
        self.assertEqual([lead.id for lead in leads], [with_coords])

    def test_empty_database_loads_nothing(self) -> None:
        self.assertEqual(MapService(self.db.path).load_leads(), [])

    def test_missing_database_loads_nothing(self) -> None:
        self.assertEqual(MapService("/nonexistent/leads.sqlite").load_leads(), [])

    def test_option_values(self) -> None:
        self._add_geolocated("A", 30.2, -97.7, score=80, priority="Hot")
        self._add_geolocated("B", 32.7, -96.8, score=50, priority="Cold")
        values = self.service.option_values(self.service.load_leads())
        self.assertEqual(values["cities"], ["Austin"])
        self.assertEqual(values["states"], ["TX"])

    def test_filter_integration(self) -> None:
        hot = self._add_geolocated("Hot One", 30.2, -97.7, score=80, priority="Hot")
        self._add_geolocated("Cold One", 32.7, -96.8, score=40, priority="Cold")
        leads = self.service.load_leads()
        filtered = self.service.filter(
            leads,
            min_lead_score=70,
            priority_labels=["Hot"],
            only_with_coordinates=True,
        )
        self.assertEqual([lead.id for lead in filtered], [hot])

    def test_dashboard_style_filter_dict(self) -> None:
        """The exact filter dict the map page builds must work end-to-end."""
        self._add_geolocated("Hot One", 30.2, -97.7, score=80, priority="Hot")
        self._add_geolocated("Warm One", 32.7, -96.8, score=55, priority="Warm")
        leads = self.service.load_leads()
        filters = {
            "min_lead_score": 60,
            "priority_labels": [],
            "categories": [],
            "cities": [],
            "states": [],
            "platforms": [],
            "has_website": None,
            "has_contact": None,
            "only_with_coordinates": True,
        }
        self.assertEqual([lead.id for lead in self.service.filter(leads, **filters)], [1])

    def test_render_returns_osm_html(self) -> None:
        if not folium_available():
            self.skipTest("folium not installed")
        lead_id = self._add_geolocated("Render Me", 30.2, -97.7)
        leads = self.service.load_leads()
        html = self.service.render(leads, cluster=True)
        self.assertIsNotNone(html)
        assert html is not None
        self.assertIn("openstreetmap.org", html)
        self.assertIn("Render Me", html)
        self.assertEqual(lead_id, leads[0].id)

    def test_render_none_when_no_coordinates(self) -> None:
        self.db.add_lead(name="No Coords")
        leads = self.service.load_leads()
        self.assertEqual(leads, [])
        self.assertIsNone(self.service.render(leads))

    def test_render_none_when_filtered_out(self) -> None:
        self._add_geolocated("Hot One", 30.2, -97.7, score=80, priority="Hot")
        leads = self.service.load_leads()
        self.assertIsNone(self.service.render(self.service.filter(leads, min_lead_score=95)))

    def test_filter_preserves_fixture_cohort(self) -> None:
        cohort = map_leads()
        matched = self.service.filter(
            cohort,
            min_lead_score=50,
            categories=["Restaurant"],
            has_website=True,
            only_with_coordinates=True,
        )
        self.assertEqual([lead.id for lead in matched], [1])

    def test_map_lead_fixture_shape(self) -> None:
        lead = map_lead(9, name="Fixture")
        self.assertEqual(lead.business_name, "Fixture")
        self.assertEqual(lead.id, 9)


if __name__ == "__main__":
    unittest.main()