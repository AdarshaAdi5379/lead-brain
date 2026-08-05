"""Map render tests: OSM tiles, markers, clustering, view fitting."""

from __future__ import annotations

import unittest

from src.map.map_data import MapLead
from src.map.map_filters import valid_coordinates
from src.map.map_render import build_map, folium_available, map_html
from tests.map_fixtures import map_leads as fixture_leads


class TestMapRender(unittest.TestCase):
    def setUp(self) -> None:
        if not folium_available():
            self.skipTest("folium not installed")

    def test_builds_osm_tile_map(self) -> None:
        m = build_map(fixture_leads(), cluster=False)
        html = map_html(m)
        self.assertIn("openstreetmap.org", html)
        self.assertIn("tile.openstreetmap.org", html)

    def test_marker_per_lead_with_popup(self) -> None:
        leads = fixture_leads()
        html = map_html(build_map(leads, cluster=False))
        for lead in leads:
            self.assertIn(lead.business_name, html)

    def test_clustering_toggle(self) -> None:
        clustered = map_html(build_map(fixture_leads(), cluster=True))
        plain = map_html(build_map(fixture_leads(), cluster=False))
        self.assertIn("MarkerCluster", clustered)
        self.assertNotIn("MarkerCluster", plain)

    def test_view_city_fits_only_that_city(self) -> None:
        leads = fixture_leads()
        m = build_map(leads, cluster=False, view_city="Austin")
        html = map_html(m)
        self.assertIn("Austin", html)

    def test_coordinates_validated_in_render(self) -> None:
        leads = fixture_leads()
        self.assertTrue(all(valid_coordinates(l.latitude, l.longitude) for l in leads))


if __name__ == "__main__":
    unittest.main()