"""Query model tests: validation, filters whitelist, keyword scoring."""

from __future__ import annotations

import unittest

from src.search.query import (
    SearchError,
    SearchQuery,
    build_metadata_filter,
    keyword_score,
    tokenize,
    validate_filters,
    validate_query,
)


class TestValidateQuery(unittest.TestCase):
    def test_normalizes_and_passes_through(self) -> None:
        query = validate_query(SearchQuery(text="  pizza  ", mode=" HYBRID "))
        self.assertEqual(query.text, "pizza")
        self.assertEqual(query.mode, "hybrid")

    def test_empty_text_keyword_mode(self) -> None:
        with self.assertRaises(SearchError):
            validate_query(SearchQuery(text="", mode="keyword"))

    def test_empty_text_semantic_mode_allowed(self) -> None:
        query = validate_query(SearchQuery(text="", mode="semantic"))
        self.assertEqual(query.text, "")

    def test_unknown_mode(self) -> None:
        with self.assertRaises(SearchError):
            validate_query(SearchQuery(text="x", mode="bogus"))

    def test_top_k_bounds(self) -> None:
        with self.assertRaises(SearchError):
            validate_query(SearchQuery(text="x", top_k=0))
        with self.assertRaises(SearchError):
            validate_query(SearchQuery(text="x", top_k=501))
        self.assertEqual(validate_query(SearchQuery(text="x", top_k=5)).top_k, 5)

    def test_negative_offset(self) -> None:
        with self.assertRaises(SearchError):
            validate_query(SearchQuery(text="x", offset=-1))

    def test_max_chars(self) -> None:
        with self.assertRaises(SearchError):
            validate_query(SearchQuery(text="x" * 501), max_query_chars=500)
        self.assertEqual(
            validate_query(SearchQuery(text="x" * 500), max_query_chars=500).text,
            "x" * 500,
        )


class TestValidateFilters(unittest.TestCase):
    def test_unknown_filter_rejected(self) -> None:
        with self.assertRaises(SearchError):
            validate_filters({"evil": "x"})
        with self.assertRaises(SearchError):
            validate_filters({"category; DROP TABLE": "x"})

    def test_string_filter_requires_string(self) -> None:
        with self.assertRaises(SearchError):
            validate_filters({"category": 42})
        with self.assertRaises(SearchError):
            validate_filters({"category": ""})
        self.assertEqual(validate_filters({"category": "  Plumber "}), {"category": "Plumber"})

    def test_bool_filter(self) -> None:
        with self.assertRaises(SearchError):
            validate_filters({"website_present": "yes"})
        self.assertEqual(validate_filters({"website_present": True}), {"website_present": True})

    def test_list_filter(self) -> None:
        with self.assertRaises(SearchError):
            validate_filters({"technologies": []})
        with self.assertRaises(SearchError):
            validate_filters({"technologies": "wordpress"})
        self.assertEqual(
            validate_filters({"technologies": [" WordPress ", "PHP"]}),
            {"technologies": ["WordPress", "PHP"]},
        )

    def test_range_filter(self) -> None:
        filters = validate_filters({"seo_score": {"min": 10, "max": 80}})
        self.assertEqual(filters, {"seo_score": {"min": 10, "max": 80}})
        with self.assertRaises(SearchError):
            validate_filters({"seo_score": 5})

    def test_overlong_value_rejected(self) -> None:
        with self.assertRaises(SearchError):
            validate_filters({"category": "x" * 300})

    def test_keys_lowercased(self) -> None:
        self.assertEqual(validate_filters({"Category": "Plumber"}), {"category": "Plumber"})


class TestBuildMetadataFilter(unittest.TestCase):
    def test_exact(self) -> None:
        self.assertEqual(build_metadata_filter({"category": "Plumber"}), {"category": "Plumber"})

    def test_range_bounds(self) -> None:
        self.assertEqual(
            build_metadata_filter({"seo_score": {"min": 10, "max": 80}}),
            {"seo_score": {"$gte": 10, "$lte": 80}},
        )
        self.assertEqual(
            build_metadata_filter({"seo_score": {"min": 10}}),
            {"seo_score": {"$gte": 10}},
        )

    def test_list_becomes_in(self) -> None:
        self.assertEqual(
            build_metadata_filter({"technologies": ["wordpress"]}),
            {"technologies": {"$in": ["wordpress"]}},
        )


class TestKeywordScoring(unittest.TestCase):
    def test_tokenize(self) -> None:
        self.assertEqual(tokenize("  Pizza Place, Austin!! "), ["pizza", "place", "austin"])

    def test_exact_match_scores_highest(self) -> None:
        tokens = tokenize("outdated website")
        exact = keyword_score(tokens, "outdated website")
        partial = keyword_score(tokens, "website redesign")
        self.assertGreater(exact, partial)
        self.assertGreater(partial, 0.0)

    def test_no_overlap_is_zero(self) -> None:
        self.assertEqual(keyword_score(tokenize("pizza"), "plumbing austin"), 0.0)

    def test_empty_inputs(self) -> None:
        self.assertEqual(keyword_score([], "text"), 0.0)
        self.assertEqual(keyword_score(["x"], ""), 0.0)


if __name__ == "__main__":
    unittest.main()
