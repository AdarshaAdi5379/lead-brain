import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.discovery import _http
from src.discovery.base import ProviderError
from src.discovery.cache import DiskCache
from src.discovery.nominatim import geocode, reverse_geocode
from src.discovery.osm import (
    OpenStreetMapProvider,
    _bbox_around,
    _build_overpass_query,
    _element_to_candidate,
    normalize_category,
    overpass_tag_filters,
)
from src.discovery.models import DiscoveryQuery


class TestCategoryMapping(unittest.TestCase):
    def test_known_categories(self) -> None:
        self.assertIn(("craft", "plumber"), overpass_tag_filters("plumber"))
        self.assertIn(("amenity", "restaurant"), overpass_tag_filters("Restaurant"))
        self.assertIn(("shop", "hairdresser"), overpass_tag_filters("salon"))
        self.assertIn(("leisure", "fitness_centre"), overpass_tag_filters("gym"))

    def test_unknown_category_falls_back_to_name(self) -> None:
        self.assertEqual(overpass_tag_filters("snake catcher"), [("name", "snake catcher")])

    def test_normalize_lowercases(self) -> None:
        self.assertEqual(normalize_category("  Plumber "), "plumber")


class TestOverpassQueryBuilder(unittest.TestCase):
    def test_query_contains_tags_and_bbox(self) -> None:
        ql = _build_overpass_query(
            category="plumber",
            south=10.0,
            west=20.0,
            north=11.0,
            east=21.0,
            cap=50,
        )
        self.assertIn('nw["craft"="plumber"](10.0,20.0,11.0,21.0);', ql)
        self.assertIn("out center tags 50;", ql)

    def test_query_fallback_name_restricted_to_poi(self) -> None:
        ql = _build_overpass_query(
            category="rare_unknown_business",
            south=10.0,
            west=20.0,
            north=11.0,
            east=21.0,
            cap=20,
        )
        self.assertIn('nw["name"~"rare_unknown_business",i][~"^(amenity|shop|office|craft|healthcare|tourism|leisure|commercial)$"~"."](10.0,20.0,11.0,21.0);', ql)

    def test_bbox_around_is_roughly_correct(self) -> None:
        s, w, n, e = _bbox_around(0.0, 0.0, 111_320)
        self.assertAlmostEqual(s, -1.0, places=5)
        self.assertAlmostEqual(n, 1.0, places=5)


class TestOverpassElementParsing(unittest.TestCase):
    def test_node_tags_and_url_normalization(self) -> None:
        element = {
            "type": "node",
            "id": 123,
            "lat": 30.1,
            "lon": -97.7,
            "tags": {
                "name": "Ace Plumbing",
                "craft": "plumber",
                "phone": "+1-512-555-0100",
                "website": "https://www.aceplumbing.com/contact?utm_source=gmb",
                "addr:city": "Austin",
                "addr:state": "TX",
                "addr:street": "1st St",
                "addr:housenumber": "100",
                "addr:postcode": "78701",
                "opening_hours": "Mo-Fr 08:00-17:00",
            },
        }
        candidate = _element_to_candidate(element, "plumber")
        self.assertIsNotNone(candidate)
        self.assertEqual(candidate.business_name, "Ace Plumbing")
        self.assertEqual(candidate.phone, "+1-512-555-0100")
        self.assertEqual(candidate.url, "https://aceplumbing.com/contact")
        self.assertEqual(candidate.city, "Austin")
        self.assertEqual(candidate.latitude, 30.1)
        self.assertEqual(candidate.longitude, -97.7)
        self.assertEqual(candidate.osm_id, "123")
        self.assertEqual(candidate.osm_type, "node")
        self.assertEqual(candidate.source, "openstreetmap")
        self.assertEqual(candidate.address, "100 1st St, Austin, 78701")

    def test_contact_style_and_center(self) -> None:
        element = {
            "type": "way",
            "id": 999,
            "center": {"lat": 32.7, "lon": -96.8},
            "tags": {"name": "Dallas Diner", "contact:email": "orders@diner.com"},
        }
        candidate = _element_to_candidate(element, "restaurant")
        self.assertIsNotNone(candidate)
        self.assertEqual(candidate.email, "orders@diner.com")
        self.assertEqual(candidate.latitude, 32.7)
        self.assertEqual(candidate.longitude, -96.8)

    def test_element_without_name_is_skipped(self) -> None:
        self.assertIsNone(
            _element_to_candidate({"type": "node", "id": 1, "tags": {}}, "plumber")
        )


class TestOpenStreetMapProvider(unittest.TestCase):
    @patch("src.discovery.osm.geocode")
    def test_geocode_failure_raises_actionable_error(self, mock_geocode) -> None:
        mock_geocode.return_value = None
        provider = OpenStreetMapProvider()
        with self.assertRaises(ProviderError) as ctx:
            provider.search(DiscoveryQuery(category="plumber", location="Nope, XX"))
        self.assertIn("Could not geocode", str(ctx.exception))

    @patch("src.discovery.osm.geocode")
    def test_search_uses_cache_and_parses_candidates(self, mock_geocode) -> None:
        mock_geocode.return_value = _BBox((10.0, 20.0, 11.0, 21.0))
        provider = OpenStreetMapProvider()
        provider._cache = _StubCache(
            [
                {
                    "type": "node",
                    "id": 1,
                    "lat": 30.1,
                    "lon": -97.7,
                    "tags": {"name": "Ace Plumbing", "phone": "555-0100"},
                },
                {
                    "type": "node",
                    "id": 2,
                    "lat": 30.2,
                    "lon": -97.8,
                    "tags": {"name": "Bob's Plumbing", "website": "https://bob.example.com"},
                },
            ]
        )
        candidates = provider.search(DiscoveryQuery(category="plumber", location="Austin, TX"))
        self.assertEqual(len(candidates), 2)
        # Prioritization puts Bob's Plumbing first because it has a website
        self.assertEqual(candidates[0].business_name, "Bob's Plumbing")
        self.assertEqual(candidates[1].business_name, "Ace Plumbing")

    @patch("src.discovery.osm.geocode")
    def test_search_overpass_failure_falls_back_to_nominatim(self, mock_geocode) -> None:
        mock_geocode.return_value = _BBox((10.0, 20.0, 11.0, 21.0))
        provider = OpenStreetMapProvider()
        provider._cache = _NoCache()
        # Mock _http.post_form to fail on all endpoints
        provider._http.post_form = lambda url, data: (_ for _ in ()).throw(RuntimeError("connection refused"))
        # Mock _search_nominatim to return candidates
        from src.discovery.base import BusinessCandidate
        provider._search_nominatim = lambda cat, loc, cap: [
            BusinessCandidate(business_name="Fallback Interiors", category=cat, url="https://fallback.com", phone="123")
        ]
        candidates = provider.search(DiscoveryQuery(category="interiors", location="Bangalore"))
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].business_name, "Fallback Interiors")
        self.assertEqual(candidates[0].url, "https://fallback.com")


class _BBox:
    def __init__(self, bbox) -> None:
        self.bbox = bbox
        self.lat = 10.5
        self.lon = 20.5


class _StubCache:
    def __init__(self, elements) -> None:
        self._elements = elements

    def get(self, key):
        return self._elements

    def set(self, key, value) -> None:
        pass


class _NoCache:
    def get(self, key):
        return None

    def set(self, key, value) -> None:
        pass


class TestDiskCache(unittest.TestCase):
    def test_get_set_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cache = DiskCache(Path(tmp), ttl_hours=24)
            cache.set("k", [1, 2, {"a": "b"}])
            self.assertEqual(cache.get("k"), [1, 2, {"a": "b"}])

    def test_zero_ttl_is_always_a_miss(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cache = DiskCache(Path(tmp), ttl_hours=0)
            cache.set("k", "v")
            self.assertIsNone(cache.get("k"))

    def test_cache_key_stable_and_unique(self) -> None:
        self.assertEqual(_http.cache_key("a", 1), _http.cache_key("a", 1))
        self.assertNotEqual(_http.cache_key("a", 1), _http.cache_key("b", 1))


class TestNominatim(unittest.TestCase):
    def setUp(self) -> None:
        self.cache_patch = patch("src.discovery.nominatim._cache", new=_NoCache())
        self.cache_patch.start()

    def tearDown(self) -> None:
        self.cache_patch.stop()
    @patch("src.discovery.nominatim._harness")
    def test_geocode_parses_bbox_and_country(self, mock_harness) -> None:
        mock_harness.get_json.return_value = [
            {
                "place_id": "999",
                "lat": "30.2672",
                "lon": "-97.7431",
                "display_name": "Austin, Travis County, Texas, United States",
                "boundingbox": ["30.1", "97.9", "30.4", "97.6"],
            }
        ]
        result = geocode("Austin, TX")
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result.lat, 30.2672, places=3)
        self.assertEqual(result.country, "United States")

    @patch("src.discovery.nominatim._harness")
    def test_geocode_empty_returns_none(self, mock_harness) -> None:
        mock_harness.get_json.return_value = []
        self.assertIsNone(geocode("Atlantis"))

    @patch("src.discovery.nominatim._harness")
    def test_geocode_unreachable_raises_provider_error(self, mock_harness) -> None:
        mock_harness.get_json.side_effect = RuntimeError("timeout")
        with self.assertRaises(ProviderError):
            geocode("Austin, TX")

    @patch("src.discovery.nominatim._harness")
    def test_reverse_geocode(self, mock_harness) -> None:
        mock_harness.get_json.return_value = [
            {"display_name": "Texas, United States", "lat": "30", "lon": "-97"}
        ]
        result = reverse_geocode(30.0, -97.0)
        self.assertIsNotNone(result)
        self.assertEqual(result.country, "United States")


if __name__ == "__main__":
    unittest.main()