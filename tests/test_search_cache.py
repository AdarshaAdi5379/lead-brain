"""Embedding cache tests: hashes, LRU bounds, reindex decisions."""

from __future__ import annotations

import unittest

from src.search.cache import EmbeddingCache, document_hash, embedding_hash, should_reindex


class TestDocumentHash(unittest.TestCase):
    def test_stable_and_content_sensitive(self) -> None:
        self.assertEqual(document_hash("hello world"), document_hash("hello world"))
        self.assertNotEqual(document_hash("hello world"), document_hash("hello world!"))
        self.assertEqual(len(document_hash("x")), 64)

    def test_empty_text_hashes(self) -> None:
        self.assertEqual(document_hash(""), document_hash(None))

    def test_embedding_hash_stable(self) -> None:
        vector = [0.1, -0.2, 0.3]
        self.assertEqual(embedding_hash(vector), embedding_hash([0.1, -0.2, 0.3]))
        self.assertNotEqual(embedding_hash(vector), embedding_hash([0.1, -0.2, 0.4]))


class TestEmbeddingCache(unittest.TestCase):
    def test_put_and_get(self) -> None:
        cache = EmbeddingCache(max_entries=4)
        vector = [0.5, 0.5]
        key = document_hash("text")
        self.assertIsNone(cache.get(key))
        cache.put(key, vector)
        self.assertEqual(cache.get(key), vector)
        self.assertEqual(len(cache), 1)

    def test_put_does_not_duplicate(self) -> None:
        cache = EmbeddingCache()
        key = document_hash("text")
        cache.put(key, [1.0])
        cache.put(key, [2.0])
        self.assertEqual(len(cache), 1)
        self.assertEqual(cache.get(key), [1.0])

    def test_fifo_eviction(self) -> None:
        cache = EmbeddingCache(max_entries=2)
        first = document_hash("a")
        cache.put(first, [1.0])
        cache.put(document_hash("b"), [2.0])
        cache.put(document_hash("c"), [3.0])
        self.assertIsNone(cache.get(first))
        self.assertEqual(len(cache), 2)

    def test_clear(self) -> None:
        cache = EmbeddingCache()
        cache.put(document_hash("a"), [1.0])
        cache.clear()
        self.assertEqual(len(cache), 0)

    def test_invalid_max_entries(self) -> None:
        with self.assertRaises(ValueError):
            EmbeddingCache(max_entries=0)


class TestShouldReindex(unittest.TestCase):
    def test_missing_row_needs_indexing(self) -> None:
        self.assertTrue(should_reindex(None, document_hash="h", embedder_id="e"))

    def test_unchanged_row_is_reused(self) -> None:
        row = {"document_hash": "h", "embedder_id": "e"}
        self.assertFalse(should_reindex(row, document_hash="h", embedder_id="e"))

    def test_content_change_triggers_reindex(self) -> None:
        row = {"document_hash": "old", "embedder_id": "e"}
        self.assertTrue(should_reindex(row, document_hash="new", embedder_id="e"))

    def test_embedder_change_triggers_reindex(self) -> None:
        row = {"document_hash": "h", "embedder_id": "old"}
        self.assertTrue(should_reindex(row, document_hash="h", embedder_id="new"))


if __name__ == "__main__":
    unittest.main()
