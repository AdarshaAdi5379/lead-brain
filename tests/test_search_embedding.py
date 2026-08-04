"""Embedding engine tests: determinism, normalization, similarity, edge cases."""

from __future__ import annotations

import unittest

from src.search.embedding import HashingEmbedder

from tests.search_fixtures import test_embedder


class TestHashingEmbedder(unittest.TestCase):
    def setUp(self) -> None:
        self.embedder = test_embedder()

    def test_dimensions(self) -> None:
        self.assertEqual(self.embedder.dimension, 512)
        self.assertTrue(self.embedder.name.startswith("hash-ngram-512"))

    def test_deterministic(self) -> None:
        text = "Pizza restaurant with poor SEO in Austin Texas"
        self.assertEqual(self.embedder.embed_one(text), self.embedder.embed_one(text))
        self.assertEqual(self.embedder.embed([text])[0], self.embedder.embed([text])[0])

    def test_vectors_are_l2_normalized(self) -> None:
        vector = self.embedder.embed_one("wordpress plumber austin texas")
        norm = sum(value * value for value in vector) ** 0.5
        self.assertAlmostEqual(norm, 1.0, places=6)

    def test_identical_texts_are_identical(self) -> None:
        vector = self.embedder.embed_one("landscaping company")
        same = self.embedder.embed_one("landscaping company")
        self.assertEqual(vector, same)

    def test_empty_text_is_zero_vector(self) -> None:
        self.assertEqual(self.embedder.embed_one(""), [0.0] * 512)
        self.assertEqual(self.embedder.embed_one(None), [0.0] * 512)

    def test_unrelated_texts_have_low_similarity(self) -> None:
        a = self.embedder.embed_one("wordpress plumber austin texas")
        b = self.embedder.embed_one("vegan bakery boston massachusetts")
        dot = sum(x * y for x, y in zip(a, b))
        self.assertLess(dot, 0.5)

    def test_related_texts_have_high_similarity(self) -> None:
        a = self.embedder.embed_one("restaurant with outdated website")
        b = self.embedder.embed_one("restaurant website redesign opportunity")
        dot = sum(x * y for x, y in zip(a, b))
        self.assertGreater(dot, 0.35)

    def test_inflections_share_features(self) -> None:
        a = self.embedder.embed_one("restaurant")
        b = self.embedder.embed_one("restaurants")
        dot = sum(x * y for x, y in zip(a, b))
        self.assertGreater(dot, 0.5)

    def test_batch_matches_single(self) -> None:
        texts = ["pizza", "plumbing", ""]
        batch = self.embedder.embed(texts, batch_size=2)
        self.assertEqual(len(batch), 3)
        self.assertEqual(batch[0], self.embedder.embed_one(texts[0]))
        self.assertEqual(batch[1], self.embedder.embed_one(texts[1]))

    def test_invalid_dimensions(self) -> None:
        with self.assertRaises(ValueError):
            HashingEmbedder(dimensions=0)
        with self.assertRaises(ValueError):
            HashingEmbedder(dimensions=-5)

    def test_name_encodes_dimensions(self) -> None:
        self.assertEqual(HashingEmbedder(dimensions=256).name, "hash-ngram-256")


if __name__ == "__main__":
    unittest.main()
