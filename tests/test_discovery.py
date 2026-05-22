import json
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.discovery.discovery import (
    DiscoveryQuery,
    discover_to_seeds,
    load_discovery_queries_csv,
)
from src.discovery.places import (
    GooglePlacesError,
    PlaceCandidate,
    place_details,
    text_search,
)


class TestPlacesTextSearch(unittest.TestCase):
    def setUp(self) -> None:
        self.sample_response = {
            "results": [
                {
                    "place_id": "abc123",
                    "name": "Alice's Plumbing",
                    "formatted_address": "123 Main St, Austin, TX",
                    "rating": 4.5,
                    "user_ratings_total": 30,
                    "types": ["plumber", "store"],
                },
                {
                    "place_id": "def456",
                    "name": "Bob's HVAC",
                    "formatted_address": "456 Oak Ave, Austin, TX",
                    "rating": 3.0,
                    "user_ratings_total": 10,
                    "types": ["hvac_contractor", "store"],
                    "website": "https://bobshvac.com",
                },
            ],
            "status": "OK",
        }

    @patch("src.discovery.places._api_key", return_value="fake-key")
    @patch("src.discovery.places._get_json")
    def test_text_search_returns_candidates(self, mock_get_json, mock_key) -> None:
        mock_get_json.return_value = self.sample_response
        results = text_search("plumber", "Austin, TX")
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0].place_id, "abc123")
        self.assertEqual(results[0].name, "Alice's Plumbing")
        self.assertIsNone(results[0].website)
        self.assertEqual(results[1].website, "https://bobshvac.com")

    @patch("src.discovery.places._api_key", return_value="fake-key")
    @patch("src.discovery.places._get_json")
    def test_text_search_zero_results(self, mock_get_json, mock_key) -> None:
        mock_get_json.return_value = {"results": [], "status": "ZERO_RESULTS"}
        results = text_search("plumber", "Nowhere, XX")
        self.assertEqual(len(results), 0)

    @patch("src.discovery.places._api_key", return_value="fake-key")
    @patch("src.discovery.places._get_json")
    def test_text_search_api_error(self, mock_get_json, mock_key) -> None:
        mock_get_json.return_value = {
            "status": "INVALID_REQUEST",
            "error_message": "Invalid API key",
        }
        with self.assertRaises(GooglePlacesError):
            text_search("plumber", "Austin, TX")


class TestPlaceDetails(unittest.TestCase):
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


class TestDiscoverToSeeds(unittest.TestCase):
    @patch("src.discovery.discovery.text_search")
    def test_discover_to_seeds_deduplicates(self, mock_search) -> None:
        mock_search.return_value = [
            PlaceCandidate(
                place_id="p1",
                name="Acme Plumbing",
                address="Austin, TX",
                rating=4.0,
                user_ratings_total=20,
                phone=None,
                website="https://acmeplumbing.com",
                types=["plumber"],
                raw={},
            ),
            PlaceCandidate(
                place_id="p2",
                name="Acme Plumbing",
                address="Austin, TX",
                rating=4.0,
                user_ratings_total=20,
                phone=None,
                website="https://acmeplumbing.com",
                types=["plumber"],
                raw={},
            ),
        ]
        queries = [DiscoveryQuery(category="plumber", location="Austin, TX")]
        seeds = discover_to_seeds(queries, fetch_details=False)
        self.assertEqual(len(seeds), 1)
        self.assertEqual(seeds[0].business_name, "Acme Plumbing")

    @patch("src.discovery.discovery.text_search")
    def test_discover_to_seeds_min_rating(self, mock_search) -> None:
        mock_search.return_value = [
            PlaceCandidate(
                place_id="p1",
                name="Good Plumbing",
                address="Austin, TX",
                rating=4.5,
                user_ratings_total=20,
                phone=None,
                website="https://good.com",
                types=["plumber"],
                raw={},
            ),
            PlaceCandidate(
                place_id="p2",
                name="Bad Plumbing",
                address="Austin, TX",
                rating=2.0,
                user_ratings_total=5,
                phone=None,
                website="https://bad.com",
                types=["plumber"],
                raw={},
            ),
        ]
        queries = [DiscoveryQuery(category="plumber", location="Austin, TX")]
        seeds = discover_to_seeds(queries, fetch_details=False, min_rating=3.0)
        self.assertEqual(len(seeds), 1)
        self.assertEqual(seeds[0].business_name, "Good Plumbing")

    @patch("src.discovery.discovery.text_search")
    def test_discover_to_seeds_coverts_city_state(self, mock_search) -> None:
        mock_search.return_value = [
            PlaceCandidate(
                place_id="p1",
                name="Some Shop",
                address="123 Main, Austin, TX",
                rating=None,
                user_ratings_total=None,
                phone="555-0100",
                website=None,
                types=["store"],
                raw={},
            ),
        ]
        queries = [DiscoveryQuery(category="store", location="Austin, TX")]
        seeds = discover_to_seeds(queries, fetch_details=False)
        self.assertEqual(len(seeds), 1)
        self.assertEqual(seeds[0].city, "Austin")
        self.assertEqual(seeds[0].state, "TX")


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


if __name__ == "__main__":
    unittest.main()
