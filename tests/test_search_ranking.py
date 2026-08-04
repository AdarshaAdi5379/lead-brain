"""Ranking tests: weight normalization, score bounds, recency decay, sorting."""

from __future__ import annotations

import unittest

from src.search.ranking import RankInput, combined_score, recency_score, sort_results
from src.search.config import rank_weights

from tests.search_fixtures import test_config


class TestRankWeights(unittest.TestCase):
    def test_default_weights_normalize_to_one(self) -> None:
        weights = rank_weights(test_config())
        self.assertAlmostEqual(sum(weights), 1.0, places=6)
        self.assertEqual(len(weights), 4)

    def test_custom_weights_are_normalized(self) -> None:
        config = test_config(
            rank_weight_similarity=2, rank_weight_lead=1,
            rank_weight_opportunity=0, rank_weight_recency=0,
        )
        weights = rank_weights(config)
        self.assertAlmostEqual(sum(weights), 1.0, places=6)
        self.assertAlmostEqual(weights[0], 2 / 3, places=6)
        self.assertAlmostEqual(weights[1], 1 / 3, places=6)

    def test_zero_weights_do_not_crash(self) -> None:
        config = test_config(rank_weight_similarity=0, rank_weight_lead=0,
                             rank_weight_opportunity=0, rank_weight_recency=0)
        self.assertEqual(sum(rank_weights(config)), 1.0)

    def test_partial_weights_normalize(self) -> None:
        config = test_config(
            rank_weight_similarity=0, rank_weight_lead=1,
            rank_weight_opportunity=1, rank_weight_recency=0,
        )
        weights = rank_weights(config)
        self.assertAlmostEqual(sum(weights), 1.0, places=6)
        self.assertAlmostEqual(weights[0], 0.0, places=6)
        self.assertAlmostEqual(weights[1], 0.5, places=6)
        self.assertAlmostEqual(weights[2], 0.5, places=6)


class TestCombinedScore(unittest.TestCase):
    def test_bounds(self) -> None:
        config = test_config()
        score = combined_score(
            RankInput(similarity=2.0, lead_score=500, opportunity_score=-10, recency=3.0),
            config,
        )
        self.assertGreaterEqual(score, 0.0)
        self.assertLessEqual(score, 1.0)

    def test_missing_scores_count_as_zero(self) -> None:
        config = test_config()
        self.assertEqual(combined_score(RankInput(similarity=0.0), config), 0.0)
        with_score = combined_score(RankInput(similarity=0.0, lead_score=100), config)
        self.assertAlmostEqual(with_score, 0.25, places=6)

    def test_higher_signals_rank_higher(self) -> None:
        config = test_config()
        weak = combined_score(RankInput(similarity=0.1), config)
        strong = combined_score(RankInput(similarity=0.9), config)
        self.assertGreater(strong, weak)

    def test_recency_component(self) -> None:
        config = test_config()
        old = combined_score(
            RankInput(similarity=0.0, recency=0.0), config
        )
        fresh = combined_score(
            RankInput(similarity=0.0, recency=1.0), config
        )
        self.assertGreater(fresh, old)


class TestRecencyScore(unittest.TestCase):
    def test_empty_and_invalid(self) -> None:
        self.assertEqual(recency_score(""), 0.0)
        self.assertEqual(recency_score("not a date"), 0.0)
        self.assertEqual(recency_score(None), 0.0)

    def test_recent_is_high(self) -> None:
        from datetime import datetime, timezone
        recent = datetime.now(timezone.utc).isoformat()
        old = "2020-01-01T00:00:00+00:00"
        self.assertGreater(recency_score(recent), recency_score(old))
        self.assertLessEqual(recency_score(recent), 1.0)
        self.assertGreater(recency_score(recent), 0.9)

    def test_timestamp_with_z_suffix(self) -> None:
        self.assertGreaterEqual(recency_score("2026-07-01T12:00:00Z"), 0.0)


class TestSortResults(unittest.TestCase):
    def test_sorts_by_combined_then_similarity_then_id(self) -> None:
        config = test_config()
        results = [
            {"lead_id": 2, "combined_score": 0.5, "similarity": 0.9},
            {"lead_id": 1, "combined_score": 0.8, "similarity": 0.1},
            {"lead_id": 3, "combined_score": 0.8, "similarity": 0.2},
        ]
        ordered = sort_results(results, config)
        self.assertEqual([item["lead_id"] for item in ordered], [3, 1, 2])

    def test_missing_scores_sorted_last(self) -> None:
        config = test_config()
        results = [
            {"lead_id": 1, "combined_score": None, "similarity": 0.0},
            {"lead_id": 2, "combined_score": 0.9, "similarity": 0.9},
        ]
        ordered = sort_results(results, config)
        self.assertEqual([item["lead_id"] for item in ordered], [2, 1])


if __name__ == "__main__":
    unittest.main()
