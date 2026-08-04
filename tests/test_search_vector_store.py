"""SQLite vector store tests: upsert/query/delete/count/clear + filter matching."""

from __future__ import annotations

import unittest

from src.search.query import build_metadata_filter, validate_filters
from src.search.vector_store import SqliteVectorStore, cosine_similarity, metadata_matches

from tests.search_fixtures import SearchTestDb


def _vector(index: int, dim: int = 8) -> list[float]:
    vector = [0.0] * dim
    vector[index % dim] = 1.0
    return vector


class TestCosineSimilarity(unittest.TestCase):
    def test_identical_vectors(self) -> None:
        self.assertAlmostEqual(cosine_similarity([1.0, 0.0], [1.0, 0.0]), 1.0)

    def test_orthogonal_vectors(self) -> None:
        self.assertAlmostEqual(cosine_similarity([1.0, 0.0], [0.0, 1.0]), 0.0)

    def test_dimension_mismatch(self) -> None:
        self.assertEqual(cosine_similarity([1.0], [1.0, 2.0]), 0.0)
        self.assertEqual(cosine_similarity([], []), 0.0)


class TestSqliteVectorStore(unittest.TestCase):
    def setUp(self) -> None:
        self.db = SearchTestDb()
        self.store = SqliteVectorStore(self.db.path)

    def tearDown(self) -> None:
        self.db.close()

    def _upsert(self, lead_id: int, vector: list[float], metadata: dict | None = None) -> None:
        self.store.upsert(
            lead_id=lead_id,
            vector=vector,
            metadata=metadata or {"lead_id": lead_id},
            document_text=f"doc {lead_id}",
            document_hash=f"hash-{lead_id}",
            embedding_hash=f"emb-{lead_id}",
            embedder_id="test",
        )

    def test_upsert_and_count(self) -> None:
        lead_id = self.db.add_lead(name="A", website="https://a.com")
        self._upsert(lead_id, _vector(0))
        self.assertEqual(self.store.count(), 1)

    def test_query_orders_by_similarity(self) -> None:
        id_a = self.db.add_lead(name="A", website="https://a.com")
        id_b = self.db.add_lead(name="B", website="https://b.com")
        id_c = self.db.add_lead(name="C", website="https://c.com")
        self._upsert(id_a, _vector(0))
        self._upsert(id_b, _vector(1))
        self._upsert(id_c, _vector(2))
        hits = self.store.query(_vector(0), top_k=3)
        self.assertEqual([hit.lead_id for hit in hits], [id_a, id_b, id_c])
        self.assertGreater(hits[0].similarity, hits[1].similarity)

    def test_query_top_k_and_where(self) -> None:
        id_a = self.db.add_lead(name="A", website="https://a.com")
        id_b = self.db.add_lead(name="B", website="https://b.com")
        self._upsert(id_a, _vector(0), {"category": "Restaurant"})
        self._upsert(id_b, _vector(0), {"category": "Plumber"})
        hits = self.store.query(_vector(0), top_k=10, where=build_metadata_filter(validate_filters({"category": "Plumber"})))
        self.assertEqual([hit.lead_id for hit in hits], [id_b])

    def test_delete_returns_truthiness(self) -> None:
        lead_id = self.db.add_lead(name="A", website="https://a.com")
        self._upsert(lead_id, _vector(0))
        self.assertFalse(self.store.delete(999))
        self.assertTrue(self.store.delete(lead_id))
        self.assertEqual(self.store.count(), 0)

    def test_clear(self) -> None:
        id_a = self.db.add_lead(name="A", website="https://a.com")
        id_b = self.db.add_lead(name="B", website="https://b.com")
        self._upsert(id_a, _vector(0))
        self._upsert(id_b, _vector(1))
        self.assertEqual(self.store.clear(), 2)
        self.assertEqual(self.store.count(), 0)

    def test_query_empty_store(self) -> None:
        self.assertEqual(self.store.query(_vector(0), top_k=5), [])


class TestMetadataMatches(unittest.TestCase):
    def test_exact_equality(self) -> None:
        self.assertTrue(metadata_matches({"category": "Plumber"}, {"category": "Plumber"}))
        self.assertFalse(metadata_matches({"category": "Plumber"}, {"category": "Baker"}))
        self.assertFalse(metadata_matches({}, {"category": "Plumber"}))

    def test_range_operators(self) -> None:
        where = {"seo_score": {"$gte": 30, "$lte": 60}}
        self.assertTrue(metadata_matches({"seo_score": 45}, where))
        self.assertFalse(metadata_matches({"seo_score": 10}, where))
        self.assertFalse(metadata_matches({}, where))

    def test_in_operator(self) -> None:
        where = {"city": {"$in": ["Austin", "Dallas"]}}
        self.assertTrue(metadata_matches({"city": "Austin"}, where))
        self.assertFalse(metadata_matches({"city": "Boston"}, where))

    def test_contains_on_list(self) -> None:
        where = {"technologies": {"$in": ["wordpress"]}}
        self.assertTrue(metadata_matches({"technologies": ["wordpress"]}, where))
        self.assertFalse(metadata_matches({"technologies": ["wix"]}, where))

    def test_contains_operator(self) -> None:
        where = {"technologies": {"$contains": "wordpress"}}
        self.assertTrue(metadata_matches({"technologies": ["wordpress", "php"]}, where))
        self.assertFalse(metadata_matches({"technologies": ["wix"]}, where))

    def test_multiple_conditions(self) -> None:
        where = {"category": "Plumber", "seo_score": {"$lt": 50}}
        self.assertTrue(metadata_matches({"category": "Plumber", "seo_score": 20}, where))
        self.assertFalse(metadata_matches({"category": "Plumber", "seo_score": 90}, where))
        self.assertFalse(metadata_matches({"category": "Baker", "seo_score": 20}, where))

    def test_empty_where_matches_everything(self) -> None:
        self.assertTrue(metadata_matches({}, {}))
        self.assertTrue(metadata_matches({"a": 1}, {}))


if __name__ == "__main__":
    unittest.main()
