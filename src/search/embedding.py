from __future__ import annotations

import hashlib
import math
import re
from abc import ABC, abstractmethod
from typing import Optional, Sequence

from src.search.config import SearchConfig

# Embedding backends for the local semantic search engine.
#
# The default ``HashingEmbedder`` is pure stdlib: deterministic, dependency-free
# and fully offline. The optional ``SentenceTransformersEmbedder`` upgrades
# semantic quality when sentence-transformers is installed (model weights are
# downloaded once from HuggingFace, then everything runs offline). Both embedders
# return L2-normalized vectors so cosine similarity works across backends.


class EmbeddingUnavailableError(RuntimeError):
    """Raised when a requested embedding backend cannot be loaded."""


_STOPWORDS = frozenset(
    """
    a an and are as at be but by for from has have he her his i if in into is it
    its me my no not of on or our she so that the their them there they this to
    too up us was we what when where which who why will with you your about
    after before between during only other some such than then these those
    through under very while
    """.split()
)

_TOKEN_RE = re.compile(r"[a-z0-9]+")


class Embedder(ABC):
    """Base contract for local embedders (text -> normalized vectors)."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Stable identifier of this embedder (used in the embedding cache)."""

    @property
    @abstractmethod
    def dimension(self) -> int:
        """Length of every produced vector."""

    @abstractmethod
    def embed(self, texts: Sequence[str], batch_size: int = 32) -> list[list[float]]:
        """Embed a batch of texts. Empty strings produce zero vectors."""

    def embed_one(self, text: str) -> list[float]:
        return self.embed([text])[0]


class HashingEmbedder(Embedder):
    """Deterministic feature-hashing n-gram embedder (pure stdlib, offline).

    Each token contributes itself plus 3-5 character n-grams (so inflections
    like "restaurants"/"restaurant" share features). Features are hashed into a
    fixed-size space with a stable keyed digest (never the per-process-randomized
    builtin ``hash()``), weighted with sublinear term frequency and
    L2-normalized. Identical input always yields identical vectors.
    """

    def __init__(self, dimensions: int = 512, stopwords: frozenset[str] = _STOPWORDS):
        if dimensions <= 0:
            raise ValueError("dimensions must be > 0")
        self._dimensions = int(dimensions)
        self._stopwords = stopwords

    @property
    def name(self) -> str:
        return f"hash-ngram-{self._dimensions}"

    @property
    def dimension(self) -> int:
        return self._dimensions

    def embed(self, texts: Sequence[str], batch_size: int = 32) -> list[list[float]]:
        del batch_size  # pure python; batching changes nothing
        return [self._embed_one(text) for text in texts]

    def _embed_one(self, text: str) -> list[float]:
        features = self._features(text)
        vector = [0.0] * self._dimensions
        counts: dict[int, tuple[int, int]] = {}
        for index, sign in features:
            count, _ = counts.get(index, (0, sign))
            counts[index] = (count + 1, sign)
        for index, (count, sign) in counts.items():
            vector[index] = (1.0 + math.log(count)) * sign
        return _l2_normalize(vector)

    def _features(self, text: str) -> list[tuple[int, int]]:
        """(index, sign) feature pairs for one document, memoized per call."""
        memo: dict[str, tuple[int, int]] = {}
        features: list[tuple[int, int]] = []
        for token in _TOKEN_RE.findall((text or "").lower()):
            if token in self._stopwords:
                continue
            for feature in _ngrams(token):
                entry = memo.get(feature)
                if entry is None:
                    entry = _stable_hash_feature(feature, self._dimensions)
                    memo[feature] = entry
                features.append(entry)
        return features


def _ngrams(token: str) -> list[str]:
    """The token itself plus 3-5 character n-grams (cheap morphology)."""
    grams = [token]
    if len(token) <= 5:
        return grams
    for size in (3, 4, 5):
        for start in range(0, len(token) - size + 1):
            grams.append(token[start : start + size])
    return grams


def _stable_hash_feature(feature: str, dimensions: int) -> tuple[int, int]:
    """Deterministic (index, sign) for a feature using a keyed digest."""
    digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=16).digest()
    index = int.from_bytes(digest[:8], "big") % dimensions
    sign = 1 if (digest[8] & 1) else -1
    return (index, sign)


def _l2_normalize(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in vector))
    if norm <= 0.0:
        return vector
    scale = 1.0 / norm
    return [value * scale for value in vector]


class SentenceTransformersEmbedder(Embedder):
    """Optional sentence-transformers embedder (best semantic quality).

    The library and model weights are loaded lazily; the model is downloaded
    from HuggingFace on first use and cached, after which everything is offline.
    Falls back to ``fallback_model`` when the primary model fails to load.
    """

    def __init__(
        self,
        model_name: str,
        *,
        device: str = "cpu",
        fallback_model: Optional[str] = None,
    ):
        try:
            from sentence_transformers import SentenceTransformer  # type: ignore
        except Exception as exc:  # pragma: no cover - optional dependency
            raise EmbeddingUnavailableError(
                "sentence-transformers is not installed. Install the optional "
                "'search' dependencies (requirements-search.txt) or use the "
                "default deterministic hash embedder."
            ) from exc

        self._model_name = model_name
        self._fallback_model = fallback_model
        self._model = self._load(model_name, device, SentenceTransformer)
        self._device = device

    def _load(self, model_name: str, device: str, sentence_transformer_cls) -> object:
        try:
            return sentence_transformer_cls(model_name, device=device)
        except Exception:
            if self._fallback_model and self._fallback_model != model_name:
                return sentence_transformer_cls(self._fallback_model, device=device)
            raise

    @property
    def name(self) -> str:
        loaded = getattr(self._model, "model_card_data", None)
        resolved = getattr(loaded, "model_name", None) or self._model_name
        return f"sentence:{resolved}"

    @property
    def dimension(self) -> int:
        return int(getattr(self._model, "get_sentence_embedding_dimension", lambda: 384)())

    def embed(self, texts: Sequence[str], batch_size: int = 32) -> list[list[float]]:
        vectors = self._model.encode(
            list(texts),
            batch_size=int(batch_size),
            normalize_embeddings=True,
            show_progress_bar=False,
            convert_to_numpy=True,
        )
        return [[float(value) for value in vector] for vector in vectors]


def get_embedder(config: SearchConfig) -> Embedder:
    """Factory: "hash" always works; "sentence" requires the optional package.

    In "auto" mode sentence-transformers is used when importable and the model
    loads, otherwise the deterministic hashing embedder is used.
    """
    mode = (config.embedder or "auto").strip().lower()
    if mode == "hash":
        return HashingEmbedder(dimensions=config.hash_dimensions)
    if mode == "sentence":
        return SentenceTransformersEmbedder(
            config.embedding_model,
            device=config.embedding_device,
            fallback_model=config.embedding_model_fallback,
        )
    try:
        return SentenceTransformersEmbedder(
            config.embedding_model,
            device=config.embedding_device,
            fallback_model=config.embedding_model_fallback,
        )
    except EmbeddingUnavailableError:
        return HashingEmbedder(dimensions=config.hash_dimensions)
