from __future__ import annotations

import logging
import sqlite3
from abc import ABC, abstractmethod
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Optional, Sequence

from src.search.config import SearchConfig
from src.storage import search as search_storage

logger = logging.getLogger("lead.search")

# Vector store backends for the local semantic search engine.
#
# The SQLite table (src/storage/search.py) is ALWAYS the canonical store: every
# backend persists the document text, hashes, metadata and the vector there, so
# search keeps working with zero optional dependencies. ChromaDB (when
# installed) is only an optional mirror/accelerator on top of it.
#
# ``where`` filters follow the Chroma dialect so both backends behave the same:
# exact equality, {"$gte": x, "$lte": y}, {"$in": [...]} and
# {"$contains": "x"} for list fields.


class StoredHit:
    """One vector-search hit (lead id + cosine similarity in 0..1)."""

    __slots__ = ("lead_id", "similarity")

    def __init__(self, lead_id: int, similarity: float):
        self.lead_id = int(lead_id)
        self.similarity = float(similarity)


class VectorStore(ABC):
    """Persistence + similarity contract shared by all backends."""

    @abstractmethod
    def upsert(
        self,
        *,
        lead_id: int,
        vector: list[float],
        metadata: dict[str, Any],
        document_text: str,
        document_hash: str,
        embedding_hash: str,
        embedder_id: str,
    ) -> None:
        """Persist (or replace) one lead's embedding across all backends."""

    @abstractmethod
    def delete(self, lead_id: int) -> bool:
        """Remove one lead's embedding. True when it existed."""

    @abstractmethod
    def query(
        self, vector: list[float], top_k: int, where: Optional[dict[str, Any]] = None
    ) -> list[StoredHit]:
        """Cosine-similarity search, best first, filtered by ``where``."""

    @abstractmethod
    def count(self) -> int:
        """Number of indexed leads."""

    @abstractmethod
    def clear(self) -> int:
        """Drop every embedding (full rebuild path). Returns removed count."""


def cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    """Cosine similarity between two vectors (both assumed L2-normalized)."""
    if not left or not right or len(left) != len(right):
        return 0.0
    return sum(a * b for a, b in zip(left, right))


class SqliteVectorStore(VectorStore):
    """Dependency-free brute-force cosine store over the canonical SQLite rows.

    Uses numpy when available for speed and falls back to pure Python; results
    are identical either way. Fast enough for 10k+ leads (chunked scans keep
    memory bounded).
    """

    def __init__(self, db_path: Path):
        self._db_path = Path(db_path)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = search_storage_connect(self._db_path)
        try:
            yield connection
        finally:
            connection.close()

    def upsert(
        self,
        *,
        lead_id: int,
        vector: list[float],
        metadata: dict[str, Any],
        document_text: str,
        document_hash: str,
        embedding_hash: str,
        embedder_id: str,
    ) -> None:
        with self._connect() as connection:
            search_storage.upsert_embedding(
                connection,
                lead_id=lead_id,
                document_hash=document_hash,
                embedding_hash=embedding_hash,
                embedder_id=embedder_id,
                document_text=document_text,
                metadata=metadata,
                embedding=vector,
            )

    def delete(self, lead_id: int) -> bool:
        with self._connect() as connection:
            return search_storage.delete_embedding(connection, lead_id)

    def query(
        self, vector: list[float], top_k: int, where: Optional[dict[str, Any]] = None
    ) -> list[StoredHit]:
        with self._connect() as connection:
            rows = search_storage.all_embedding_rows(connection)
        candidates = [
            row
            for row in rows
            if where is None or metadata_matches(row.get("metadata") or {}, where)
        ]
        if not candidates:
            return []

        vectors = [row.get("embedding") or [] for row in candidates]
        try:
            import numpy as np  # type: ignore

            query_vec = np.asarray(vector, dtype=np.float64)
            matrix = np.asarray(vectors, dtype=np.float64)
            if matrix.ndim == 2 and matrix.shape[1] == query_vec.shape[0] and matrix.size:
                scores = matrix @ query_vec
            else:
                scores = [
                    cosine_similarity(vector, candidate)
                    for candidate in vectors
                ]
        except Exception:  # pragma: no cover - numpy optional
            scores = [cosine_similarity(vector, candidate) for candidate in vectors]

        order = sorted(
            range(len(candidates)), key=lambda i: scores[i], reverse=True
        )[: max(0, int(top_k))]
        return [
            StoredHit(lead_id=int(candidates[i]["lead_id"]), similarity=float(scores[i]))
            for i in order
        ]

    def count(self) -> int:
        with self._connect() as connection:
            return search_storage.count_embeddings(connection)

    def clear(self) -> int:
        with self._connect() as connection:
            return search_storage.clear_embeddings(connection)


class ChromaVectorStore(VectorStore):
    """Optional ChromaDB-backed store (persistent local, no cloud, telemetry off).

    The canonical SQLite row is still written (see module docstring); Chroma is
    the ANN accelerator used when ``SEARCH_VECTOR_STORE`` resolves to it.
    """

    COLLECTION_NAME = "lead_embeddings"

    def __init__(self, chroma_dir: Path, db_path: Path):
        import chromadb  # type: ignore
        from chromadb.config import Settings  # type: ignore

        chroma_dir = Path(chroma_dir)
        chroma_dir.mkdir(parents=True, exist_ok=True)
        self._db_path = Path(db_path)
        try:
            self._client = chromadb.PersistentClient(
                path=str(chroma_dir),
                settings=Settings(anonymized_telemetry=False, allow_reset=True),
            )
        except Exception:  # pragma: no cover - defensive
            self._client = chromadb.PersistentClient(path=str(chroma_dir))
        self._collection = self._client.get_or_create_collection(
            name=self.COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )

    def _canonical(self, lead_id: int) -> Iterator[sqlite3.Connection]:
        del lead_id
        connection = search_storage_connect(self._db_path)
        try:
            yield connection
        finally:
            connection.close()

    def upsert(
        self,
        *,
        lead_id: int,
        vector: list[float],
        metadata: dict[str, Any],
        document_text: str,
        document_hash: str,
        embedding_hash: str,
        embedder_id: str,
    ) -> None:
        with self._canonical(lead_id) as connection:
            search_storage.upsert_embedding(
                connection,
                lead_id=lead_id,
                document_hash=document_hash,
                embedding_hash=embedding_hash,
                embedder_id=embedder_id,
                document_text=document_text,
                metadata=metadata,
                embedding=vector,
            )
        sanitized = {key: value for key, value in metadata.items() if value is not None}
        self._collection.upsert(
            ids=[str(int(lead_id))],
            embeddings=[vector],
            metadatas=[sanitized],
            documents=[document_text],
        )

    def delete(self, lead_id: int) -> bool:
        removed = False
        with self._canonical(lead_id) as connection:
            removed = search_storage.delete_embedding(connection, lead_id)
        try:
            self._collection.delete(ids=[str(int(lead_id))])
        except Exception:  # pragma: no cover - missing id
            pass
        return removed

    def query(
        self, vector: list[float], top_k: int, where: Optional[dict[str, Any]] = None
    ) -> list[StoredHit]:
        limit = min(max(0, int(top_k)), max(1, self._collection.count()))
        if limit == 0:
            return []
        result = self._collection.query(
            query_embeddings=[vector],
            n_results=limit,
            where=where if where else None,
            include=["distances"],
        )
        ids = (result.get("ids") or [[]])[0]
        distances = (result.get("distances") or [[]])[0]
        hits: list[StoredHit] = []
        for raw_id, distance in zip(ids, distances):
            try:
                lead_id = int(str(raw_id))
            except (TypeError, ValueError):  # pragma: no cover - defensive
                continue
            hits.append(StoredHit(lead_id=lead_id, similarity=1.0 - float(distance)))
        return hits

    def count(self) -> int:
        return self._collection.count()

    def clear(self) -> int:
        removed = 0
        with self._canonical(0) as connection:
            removed = search_storage.clear_embeddings(connection)
        try:
            self._client.delete_collection(self.COLLECTION_NAME)
        except Exception:  # pragma: no cover
            pass
        self._collection = self._client.get_or_create_collection(
            name=self.COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
        return removed


def search_storage_connect(db_path: Path) -> sqlite3.Connection:
    """Open a fresh SQLite connection to the leads database (Row factory).

    The schema is (re)created cheaply on every connect so the search stores are
    self-sufficient against a missing or uninitialized database file.
    """
    connection = sqlite3.connect(Path(db_path))
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON;")
    from src.storage.db import init_db

    init_db(connection)
    return connection


def get_vector_store(config: SearchConfig, db_path: Path) -> VectorStore:
    """Factory for the configured vector store backend.

    "sqlite" always works; "chroma" requires the optional package; "auto"
    prefers chromadb when importable and falls back to SQLite otherwise.
    """
    mode = (config.vector_store or "auto").strip().lower()
    if mode == "sqlite":
        return SqliteVectorStore(db_path)
    if mode == "chroma":
        return ChromaVectorStore(config.chroma_dir, db_path)
    try:
        return ChromaVectorStore(config.chroma_dir, db_path)
    except Exception as exc:
        logger.debug("ChromaDB unavailable (%s); falling back to SQLite store", exc)
        return SqliteVectorStore(db_path)


def metadata_matches(metadata: dict[str, Any], where: dict[str, Any]) -> bool:
    """Match a metadata dict against a Chroma-dialect where clause."""
    for key, condition in where.items():
        value = metadata.get(key)
        if isinstance(condition, dict):
            for operator, operand in condition.items():
                if not _match_operator(value, operator, operand):
                    return False
        elif isinstance(condition, list):
            if not _in_condition(value, condition):
                return False
        elif value != condition:
            return False
    return True


def _match_operator(value: Any, operator: str, operand: Any) -> bool:
    if operator == "$eq":
        return value == operand
    if operator == "$ne":
        return value != operand
    if operator == "$in":
        return _in_condition(value, operand)
    if operator == "$contains":
        if isinstance(value, (list, tuple)):
            return operand in value
        return False
    if operator in ("$gte", "$gt", "$lte", "$lt"):
        if value is None:
            return False
        try:
            return {
                "$gte": value >= operand,
                "$gt": value > operand,
                "$lte": value <= operand,
                "$lt": value < operand,
            }[operator]
        except TypeError:
            return False
    return False


def _in_condition(value: Any, options: Sequence[Any]) -> bool:
    if isinstance(value, (list, tuple)):
        return any(item in options for item in value)
    return value in options
