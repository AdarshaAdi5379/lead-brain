import unittest
from pathlib import Path
from unittest.mock import patch

from src.discovery.discovery import (
    DiscoveryQuery,
    discover_to_seeds,
    load_discovery_queries_csv,
)
from src.discovery.base import BusinessCandidate
from src.discovery.osm import OpenStreetMapProvider
from src.discovery.places import GooglePlacesError, PlaceCandidate, place_details, text_search


def _candidate(
    name: str,
    url: str | None,
    *,
    city: str | None = None,
    category: str = "plumber",
) -> BusinessCandidate:
    return BusinessCandidate(
        business_name=name,
        category=category,
        url=url,
        city=city,
        source="openstreetmap",
        raw={},
    )


class TestDiscoverToSeeds(unittest.TestCase):
    @patch.object(OpenStreetMapProvider, "search")
    def test_deduplicates_by_url(self, mock_search) -> None:
        mock_search.return_value = [
            _candidate("Acme Plumbing", "https://acmeplumbing.com"),
            _candidate("Acme Plumbing", "https://www.acmeplumbing.com/"),
        ]
        seeds = discover_to_seeds([DiscoveryQuery(category="plumber", location="Austin, TX")])
        self.assertEqual(len(seeds), 1)
        self.assertEqual(seeds[0].business_name, "Acme Plumbing")

    @patch.object(OpenStreetMapProvider, "search")
    def test_deduplicates_missing_url_by_identity(self, mock_search) -> None:
        mock_search.return_value = [
            _candidate("Acme Plumbing", None, city="Austin"),
            _candidate("acme plumbing", None, city="Austin"),
        ]
        query = DiscoveryQuery(category="plumber", location="Austin, TX")
        seeds = discover_to_seeds([query])
        self.assertEqual(len(seeds), 1)

    @patch.object(OpenStreetMapProvider, "search")
    def test_city_state_fallback_from_query(self, mock_search) -> None:
        mock_search.return_value = [_candidate("Some Shop", None, category="store")]
        seeds = discover_to_seeds([DiscoveryQuery(category="store", location="Austin, TX")])
        self.assertEqual(len(seeds), 1)
        self.assertEqual(seeds[0].city, "Austin")
        self.assertEqual(seeds[0].state, "TX")

    @patch.object(OpenStreetMapProvider, "search")
    def test_metadata_survives_seed_conversion(self, mock_search) -> None:
        mock_search.return_value = [
            BusinessCandidate(
                business_name="Bob's HVAC",
                category="hvac",
                url="https://bobshvac.com",
                phone="+1-555-1000",
                email="bob@bobshvac.com",
                city="Dallas",
                state="TX",
                country="United States",
                latitude=32.7,
                longitude=-96.8,
                address="10 Main St, Dallas, TX",
                opening_hours="Mo-Fr 08:00-17:00",
                osm_id="123456",
                osm_type="node",
                source="openstreetmap",
                raw={},
            )
        ]
        seeds = discover_to_seeds([DiscoveryQuery(category="hvac", location="Dallas, TX")])
        self.assertEqual(len(seeds), 1)
        seed = seeds[0]
        self.assertEqual(seed.phone, "+1-555-1000")
        self.assertEqual(seed.email, "bob@bobshvac.com")
        self.assertEqual(seed.country, "United States")
        self.assertEqual(seed.latitude, 32.7)
        self.assertEqual(seed.osm_id, "123456")
        self.assertEqual(seed.source, "openstreetmap")

    @patch.object(OpenStreetMapProvider, "search")
    def test_failed_query_is_skipped_not_fatal(self, mock_search) -> None:
        def _explode(query, *, radius=None, limit=None):
            raise RuntimeError("nominatim down")

        mock_search.side_effect = _explode
        seeds = discover_to_seeds([DiscoveryQuery(category="plumber", location="Nowhere, XX")])
        self.assertEqual(seeds, [])


class TestGoogleProviderAdapter(unittest.TestCase):
    @patch("src.discovery.google.text_search")
    @patch("src.discovery.google.place_details")
    def test_google_wrapper_produces_candidates(self, mock_details, mock_search) -> None:
        mock_search.return_value = [
            PlaceCandidate("p1", "Alice's Plumbing", None, 4.5, 30, None, "https://alice.com", [], {}),
            PlaceCandidate("p2", "Bob's HVAC", "Austin, TX", 3.0, 10, None, None, [], {}),
        ]
        mock_details.return_value = PlaceCandidate(
            "p2", "Bob's HVAC", "Austin, TX", 3.0, 10, "+1-555-000", "https://bobshvac.com", [], {}
        )
        from src.discovery.google import GooglePlacesProvider

        candidates = GooglePlacesProvider().search(DiscoveryQuery(category="plumber", location="Austin, TX"))
        self.assertEqual(len(candidates), 2)
        self.assertEqual(candidates[0].source, "google")
        self.assertEqual(candidates[1].url, "https://bobshvac.com")
        self.assertEqual(candidates[1].phone, "+1-555-000")


class TestLoadDiscoveryQueriesCSV(unittest.TestCase):
    def test_loads_valid_csv(self) -> None:
        path = Path("/tmp/test_discovery_queries.csv")
        path.write_text(
            'category,location\nplumber,"Austin, TX"\nhvac,"Dallas, TX"\n',
            encoding="utf-8",
        )
        try:
            queries = load_discovery_queries_csv(path)
            self.assertEqual(len(queries), 2)
            self.assertEqual(queries[0].category, "plumber")
            self.assertEqual(queries[0].location, "Austin, TX")
        finally:
            path.unlink(missing_ok=True)

    def test_empty_csv_raises(self) -> None:
        path = Path("/tmp/test_empty_queries.csv")
        path.write_text("category,location\n", encoding="utf-8")
        try:
            with self.assertRaises(ValueError):
                load_discovery_queries_csv(path)
        finally:
            path.unlink(missing_ok=True)


class TestGooglePlacesValidation(unittest.TestCase):
    @patch("src.discovery.places._api_key", return_value="fake-key")
    @patch("src.discovery.places._get_json")
    def test_text_search_zero_results(self, mock_get_json, mock_key) -> None:
        mock_get_json.return_value = {"results": [], "status": "ZERO_RESULTS"}
        self.assertEqual(text_search("plumber", "Nowhere, XX"), [])

    @patch("src.discovery.places._api_key", return_value="fake-key")
    @patch("src.discovery.places._get_json")
    def test_text_search_api_error(self, mock_get_json, mock_key) -> None:
        mock_get_json.return_value = {"status": "INVALID_REQUEST", "error_message": "bad"}
        with self.assertRaises(GooglePlacesError):
            text_search("plumber", "Austin, TX")

    @patch("src.discovery.places._api_key", return_value="fake-key")
    @patch("src.discovery.places._get_json")
    def test_place_details_returns_enriched(self, mock_get_json, mock_key) -> None:
        mock_get_json.return_value = {
            "result": {
                "place_id": "abc123",
                "name": "Alice's Plumbing",
                "formatted_address": "123 Main St, Austin, TX",
                "rating": 4.5,
                "website": "https://alicesplumbing.com",
                "formatted_phone_number": "+1-555-123-4567",
            },
            "status": "OK",
        }
        result = place_details("abc123")
        self.assertEqual(result.website, "https://alicesplumbing.com")
        self.assertEqual(result.phone, "+1-555-123-4567")


if __name__ == "__main__":
    unittest.main()