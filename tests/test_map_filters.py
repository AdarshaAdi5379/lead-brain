"""Map filter tests: coordinate validity, score grouping, filter predicates."""

from __future__ import annotations

import unittest

from src.map.map_data import MapLead
from src.map.map_filters import filter_leads, score_group, valid_coordinates
from src.scoring.config import ScoringConfig


def _lead(
    lead_id: int,
    *,
    lat: float = 30.2,
    lon: float = -97.7,
    score: int = 62,
    priority: str = "Warm",
    category: str = "Restaurant",
    city: str = "Austin",
    state: str = "TX",
    platform: str = "WordPress",
    website: str = "https://x.com",
    contact: bool = True,
) -> MapLead:
    return MapLead(
        id=lead_id,
        business_name=f"Biz {lead_id}",
        category=category,
        city=city,
        state=state,
        platform=platform,
        latitude=lat,
        longitude=lon,
        website_url=website,
        lead_score=score,
        priority_label=priority,
        opportunity_score=80,
        has_contact=contact,
    )


class TestValidCoordinates(unittest.TestCase):
    def test_valid_ranges(self) -> None:
        self.assertTrue(valid_coordinates(30.2, -97.7))
        self.assertTrue(valid_coordinates(90, 180))
        self.assertTrue(valid_coordinates(-90, -180))
        self.assertTrue(valid_coordinates("30.5", "-97.5"))

    def test_out_of_range(self) -> None:
        self.assertFalse(valid_coordinates(91, 0))
        self.assertFalse(valid_coordinates(0, 181))
        self.assertFalse(valid_coordinates(-90.01, 0))
        self.assertFalse(valid_coordinates(0, -180.01))

    def test_missing_or_junk(self) -> None:
        self.assertFalse(valid_coordinates(None, None))
        self.assertFalse(valid_coordinates("nope", 0))
        self.assertFalse(valid_coordinates(30.2, None))

    def test_infinity_rejected(self) -> None:
        self.assertFalse(valid_coordinates(float("inf"), 0))


class TestScoreGroup(unittest.TestCase):
    def test_bands_match_scoring_config(self) -> None:
        expected = dict(ScoringConfig().priority_bands)
        self.assertEqual(score_group(80), expected[75])
        self.assertEqual(score_group(75), "Hot")
        self.assertEqual(score_group(60), "Warm")
        self.assertEqual(score_group(55), "Warm")
        self.assertEqual(score_group(40), "Cold")
        self.assertEqual(score_group(30), "Cold")
        self.assertEqual(score_group(10), "Avoid")
        self.assertEqual(score_group(0), "Avoid")

    def test_missing_score_never_raises(self) -> None:
        self.assertEqual(score_group(None), "Avoid")
        self.assertEqual(score_group("junk"), "Avoid")


class TestFilterLeads(unittest.TestCase):
    def setUp(self) -> None:
        self.leads = [
            _lead(1, score=82, priority="Hot", city="Austin"),
            _lead(2, score=61, priority="Warm", city="Round Rock"),
            _lead(3, score=35, priority="Cold", city="Austin", website=None, contact=False),
            _lead(4, lat=None, lon=None, score=70),  # no coordinates
        ]

    def test_no_filters_returns_everything(self) -> None:
        out = filter_leads(self.leads, only_with_coordinates=False)
        self.assertEqual(len(out), 4)

    def test_only_with_coordinates_drops_missing(self) -> None:
        out = filter_leads(self.leads)
        self.assertEqual([l.id for l in out], [1, 2, 3])

    def test_min_lead_score(self) -> None:
        out = filter_leads(self.leads, min_lead_score=60)
        self.assertEqual([l.id for l in out], [1, 2])

    def test_priority_labels(self) -> None:
        out = filter_leads(self.leads, priority_labels=["Hot", "Cold"])
        self.assertEqual([l.id for l in out], [1, 3])

    def test_category_city_state_platform(self) -> None:
        self.assertEqual(
            [l.id for l in filter_leads(self.leads, categories=["Restaurant"])],
            [1, 2, 3],
        )
        self.assertEqual(
            [l.id for l in filter_leads(self.leads, cities=["Austin"])], [1, 3]
        )
        self.assertEqual(
            [l.id for l in filter_leads(self.leads, states=["TX"])], [1, 2, 3]
        )
        self.assertEqual(
            [l.id for l in filter_leads(self.leads, platforms=["WordPress"])], [1, 2, 3]
        )

    def test_has_website(self) -> None:
        self.assertEqual([l.id for l in filter_leads(self.leads, has_website=True)], [1, 2])
        self.assertEqual([l.id for l in filter_leads(self.leads, has_website=False)], [3])

    def test_has_contact(self) -> None:
        self.assertEqual([l.id for l in filter_leads(self.leads, has_contact=True)], [1, 2])
        self.assertEqual([l.id for l in filter_leads(self.leads, has_contact=False)], [3])

    def test_combined(self) -> None:
        out = filter_leads(
            self.leads,
            min_lead_score=55,
            cities=["Austin"],
            has_website=True,
        )
        self.assertEqual([l.id for l in out], [1])

    def test_empty_input(self) -> None:
        self.assertEqual(filter_leads([]), [])
        self.assertEqual(filter_leads([], only_with_coordinates=False), [])


if __name__ == "__main__":
    unittest.main()