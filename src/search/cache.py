from __future__ import annotations

import hashlib
import json
from typing import Any, Optional

# Embedding caching: deterministic content hashing so unchanged lead documents
# are never re-embedded, plus a small in-process LRU for repeated lookups.

_MAX_CACHE_ENTRIES = 2048


def document_hash(text: str) -> str:
    """Stable sha256 of the semantic document text (change detection)."""
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def embedding_hash(vector: list[float]) -> str:
    """Stable sha256 of a canonical serialization of the vector."""
    canonical = json.dumps(vector, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class EmbeddingCache:
    """Bounded in-process LRU of document_hash -> vector.

    Avoids re-embedding the same content within one process (e.g. the same
    document touched by both ``index_lead`` and ``similar`` in one session).
    Deterministic eviction (FIFO) keeps behaviour reproducible.
    """

    def __init__(self, max_entries: int = _MAX_CACHE_ENTRIES):
        if max_entries <= 0:
            raise ValueError("max_entries must be > 0")
        self._max_entries = int(max_entries)
        self._data: dict[str, list[float]] = {}
        self._order: list[str] = []

    def __len__(self) -> int:
        return len(self._data)

    def get(self, document_hash: str) -> Optional[list[float]]:
        return self._data.get(document_hash)

    def put(self, document_hash: str, vector: list[float]) -> None:
        if document_hash in self._data:
            return
        self._data[document_hash] = vector
        self._order.append(document_hash)
        while len(self._order) > self._max_entries:
            oldest = self._order.pop(0)
            self._data.pop(oldest, None)

    def clear(self) -> None:
        self._data.clear()
        self._order.clear()


def should_reindex(
    existing_row: Optional[dict[str, Any]],
    *,
    document_hash: str,
    embedder_id: str,
) -> bool:
    """True when the lead must be re-embedded.

    A stored row is reusable only when its content hash AND its embedder match
    the current state. Changing the embedding backend (e.g. upgrading from the
    hash embedder to sentence-transformers) therefore invalidates every row.
    """
    if existing_row is None:
        return True
    if existing_row.get("document_hash") != document_hash:
        return True
    if existing_row.get("embedder_id") != embedder_id:
        return True
    return False
