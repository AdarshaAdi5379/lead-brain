from __future__ import annotations

import logging
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator, Optional

from src.search.cache import EmbeddingCache, embedding_hash, should_reindex
from src.search.config import SearchConfig, from_settings
from src.search.embedding import Embedder, get_embedder
from src.search.index import SearchDocument, build_lead_document
from src.search.query import SearchError, SearchQuery, build_metadata_filter, keyword_score, tokenize, validate_query
from src.search.ranking import RankInput, combined_score, recency_score, sort_results
from src.search.summarizer import build_context, context_to_text
from src.search.vector_store import VectorStore, get_vector_store
from src.storage import search as search_storage
from src.storage.db import connect, init_db

logger = logging.getLogger("lead.search")

# SearchService is the public facade for the local semantic search engine:
# incremental indexing (index_run / index_lead / update_lead / delete_lead),
# full rebuilds, semantic/keyword/hybrid search, similar-leads and the AI
# context builder. Everything is lazy: heavy backends load only when used.


@dataclass(frozen=True)
class IndexStats:
    """Outcome of one indexing operation."""

    total: int
    indexed: int
    skipped: int

    @property
    def changed(self) -> bool:
        return self.indexed > 0


@dataclass(frozen=True)
class SearchResult:
    """One ranked search hit with the card fields the dashboard renders."""

    lead_id: int
    business_name: Optional[str]
    website_url: Optional[str]
    category: Optional[str]
    city: Optional[str]
    state: Optional[str]
    country: Optional[str]
    platform: Optional[str]
    priority: Optional[str]
    lead_score: Optional[int]
    opportunity_score: Optional[int]
    seo_score: Optional[int]
    visual_score: Optional[int]
    similarity: float
    combined_score: float
    top_reasons: list[str] = field(default_factory=list)


class SearchService:
    """Local, offline semantic search over all collected lead intelligence."""

    def __init__(
        self,
        db_path: Optional[Path] = None,
        config: Optional[SearchConfig] = None,
    ):
        self._db_path = Path(db_path) if db_path is not None else None
        self._config = config or from_settings()
        self._embedder: Optional[Embedder] = None
        self._store: Optional[VectorStore] = None
        self._embedding_cache = EmbeddingCache()

    # -- lazy components ------------------------------------------------------

    @property
    def config(self) -> SearchConfig:
        return self._config

    @property
    def embedder(self) -> Embedder:
        if self._embedder is None:
            self._embedder = get_embedder(self._config)
        return self._embedder

    @property
    def store(self) -> VectorStore:
        if self._store is None:
            self._store = get_vector_store(self._config, self._db_path or Path("data/leads.sqlite"))
        return self._store

    @property
    def embedder_id(self) -> str:
        return f"{self.embedder.name}|{self.embedder.dimension}"

    # -- indexing -------------------------------------------------------------

    def index_run(self, run_id: int) -> IndexStats:
        """Incrementally index every lead of a pipeline run.

        Only documents whose content (or embedding backend) changed are
        re-embedded; unchanged leads are skipped without any embedding work.
        """
        with self._connect() as connection:
            intelligence = search_storage.leads_intelligence(connection, run_id=int(run_id))
        if not intelligence:
            return IndexStats(total=0, indexed=0, skipped=0)

        with self._connect() as connection:
            existing = {
                lead_id: search_storage.get_embedding_row(connection, lead_id)
                for lead_id in intelligence
            }
        return self._index_documents(intelligence, existing)

    def index_lead(self, lead_id: int) -> bool:
        """Index (or refresh) one lead. Returns True when it was (re)embedded."""
        with self._connect() as connection:
            intel = search_storage.lead_intelligence(connection, int(lead_id))
            if intel is None:
                return self.delete_lead(int(lead_id))
            existing_row = search_storage.get_embedding_row(connection, int(lead_id))
        stats = self._index_documents({int(lead_id): intel}, {int(lead_id): existing_row})
        return stats.indexed > 0

    def update_lead(self, lead_id: int) -> bool:
        """Refresh one lead's embedding when its document changed."""
        return self.index_lead(lead_id)

    def delete_lead(self, lead_id: int) -> bool:
        """Remove a lead from the index. True when it was indexed."""
        return self.store.delete(int(lead_id))

    def rebuild_index(self) -> IndexStats:
        """Drop the whole index and rebuild every lead (embedder-aware)."""
        self.store.clear()
        with self._connect() as connection:
            intelligence = search_storage.leads_intelligence(connection)
        return self._index_documents(intelligence, {})

    # -- search ---------------------------------------------------------------

    def search(self, query: SearchQuery) -> list[SearchResult]:
        """Semantic, keyword or hybrid search over the indexed leads."""
        validated = validate_query(query, max_query_chars=self._config.max_query_chars)
        where = build_metadata_filter(validated.filters)

        query_tokens = tokenize(validated.text) if validated.mode != "semantic" else []
        candidate_window = (validated.top_k + validated.offset) * 2

        semantic_scores: dict[int, float] = {}
        if validated.mode in ("semantic", "hybrid"):
            query_vector = self.embedder.embed_one(validated.text)
            for hit in self.store.query(query_vector, top_k=candidate_window, where=where):
                semantic_scores[hit.lead_id] = hit.similarity

        keyword_scores: dict[int, float] = {}
        if validated.mode in ("keyword", "hybrid"):
            keyword_scores = self._keyword_scores(validated.text, query_tokens, where)

        if validated.mode == "semantic":
            relevance = semantic_scores
        elif validated.mode == "keyword":
            relevance = keyword_scores
        else:
            weight = self._config.hybrid_weight
            relevance = {
                lead_id: weight * semantic_scores.get(lead_id, 0.0)
                + (1.0 - weight) * keyword_scores.get(lead_id, 0.0)
                for lead_id in set(semantic_scores) | set(keyword_scores)
            }

        if not relevance:
            return []
        top_ids = sorted(
            relevance, key=lambda lead_id: (-relevance[lead_id], lead_id)
        )[:candidate_window]
        return self._build_results(top_ids, relevance, limit=validated.top_k)

    def similar(self, lead_id: int, top_k: int = 10) -> list[SearchResult]:
        """Top similar leads (excludes the lead itself). Uses the stored vector."""
        with self._connect() as connection:
            row = search_storage.get_embedding_row(connection, int(lead_id))
        if row is None:
            if not self.index_lead(int(lead_id)):
                raise SearchError(f"Lead {lead_id} is not indexed")
            with self._connect() as connection:
                row = search_storage.get_embedding_row(connection, int(lead_id))
        if row is None or not row.get("embedding"):
            raise SearchError(f"Lead {lead_id} has no embedding")

        hits = self.store.query(
            row["embedding"], top_k=max(1, int(top_k)) + 1
        )
        similarities = {
            hit.lead_id: hit.similarity for hit in hits if hit.lead_id != int(lead_id)
        }
        if not similarities:
            return []
        ordered = sorted(
            similarities, key=lambda lid: (-similarities[lid], lid)
        )[: max(1, int(top_k))]
        return self._build_results(ordered, similarities)

    # -- AI context -----------------------------------------------------------

    def context_for_lead(self, lead_id: int) -> Optional[dict[str, Any]]:
        """Structured AI context for one lead (see src/search/summarizer.py)."""
        with self._connect() as connection:
            intel = search_storage.lead_intelligence(connection, int(lead_id))
        return build_context(intel) if intel else None

    def context_text_for_lead(self, lead_id: int) -> Optional[str]:
        context = self.context_for_lead(lead_id)
        return context_to_text(context) if context else None

    # -- stats ----------------------------------------------------------------

    def stats(self) -> dict[str, Any]:
        """Index size + backend identity (for the dashboard)."""
        return {
            "count": self.store.count(),
            "embedder": self.embedder.name,
            "embedding_dimension": self.embedder.dimension,
            "vector_store": type(self.store).__name__,
            "enabled": self._config.enabled,
        }

    def count(self) -> int:
        return self.store.count()

    # -- internals ------------------------------------------------------------

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        db_path = self._db_path or Path("data/leads.sqlite")
        connection = connect(db_path)
        init_db(connection)
        try:
            yield connection
        finally:
            connection.close()

    def _index_documents(
        self,
        intelligence: dict[int, dict[str, Any]],
        existing: dict[int, Optional[dict[str, Any]]],
    ) -> IndexStats:
        changed: list[SearchDocument] = []
        for lead_id, intel in intelligence.items():
            doc = build_lead_document(intel)
            if doc is None:
                continue
            if not should_reindex(
                existing.get(lead_id),
                document_hash=doc.document_hash,
                embedder_id=self.embedder_id,
            ):
                continue
            changed.append(doc)

        if not changed:
            return IndexStats(total=len(intelligence), indexed=0, skipped=len(intelligence))

        indexed = 0
        batch_size = max(1, int(self._config.batch_size))
        for start in range(0, len(changed), batch_size):
            batch = changed[start : start + batch_size]
            vectors = self.embedder.embed([doc.text for doc in batch], batch_size=batch_size)
            for doc, vector in zip(batch, vectors):
                self._embedding_cache.put(doc.document_hash, vector)
                self.store.upsert(
                    lead_id=doc.lead_id,
                    vector=vector,
                    metadata=doc.metadata,
                    document_text=doc.text,
                    document_hash=doc.document_hash,
                    embedding_hash=embedding_hash(vector),
                    embedder_id=self.embedder_id,
                )
                indexed += 1
        return IndexStats(
            total=len(intelligence), indexed=indexed, skipped=len(intelligence) - indexed
        )

    def _keyword_scores(
        self, text: str, query_tokens: list[str], where: dict[str, Any]
    ) -> dict[int, float]:
        if not query_tokens:
            return {}
        from src.search.vector_store import metadata_matches

        with self._connect() as connection:
            rows = search_storage.all_embedding_rows(connection)
        scores: dict[int, float] = {}
        for row in rows:
            if not metadata_matches(row.get("metadata") or {}, where):
                continue
            score = keyword_score(query_tokens, row.get("document_text") or "")
            if score > 0.0:
                scores[int(row["lead_id"])] = score
        return scores

    def _build_results(
        self,
        lead_ids: list[int],
        relevance: dict[int, float],
        limit: Optional[int] = None,
    ) -> list[SearchResult]:
        if not lead_ids:
            return []
        with self._connect() as connection:
            intelligence = search_storage.leads_intelligence(
                connection, lead_ids=lead_ids
            )
        results: list[dict[str, Any]] = []
        for lead_id in lead_ids:
            intel = intelligence.get(lead_id)
            if intel is None:
                continue
            lead = intel.get("lead") or {}
            score = intel.get("score") or {}
            opportunities = intel.get("opportunities") or []
            opportunity_score = max(
                (int(item.get("score") or 0) for item in opportunities), default=0
            ) or None
            reasons = list(score.get("top_positive_reasons") or []) + list(
                score.get("top_negative_reasons") or []
            )
            if not reasons and lead.get("last_error"):
                reasons = [str(lead["last_error"])]
            priority = str(lead.get("priority") or score.get("priority_label") or "") or None
            raw_lead_score = (
                score.get("final_score")
                if score.get("final_score") is not None
                else lead.get("score")
            )
            lead_score = int(raw_lead_score) if raw_lead_score is not None else None
            similarity = float(relevance.get(lead_id, 0.0))
            combined = combined_score(
                RankInput(
                    similarity=similarity,
                    lead_score=lead_score,
                    opportunity_score=opportunity_score,
                    recency=recency_score(str(lead.get("extracted_at") or "")),
                ),
                self._config,
            )
            results.append(
                {
                    "lead_id": int(lead_id),
                    "business_name": lead.get("business_name"),
                    "website_url": lead.get("website_url"),
                    "category": lead.get("category"),
                    "city": lead.get("city"),
                    "state": lead.get("state"),
                    "country": lead.get("country"),
                    "platform": lead.get("platform"),
                    "priority": priority,
                    "lead_score": lead_score,
                    "opportunity_score": opportunity_score,
                    "seo_score": (
                        int((intel.get("seo") or {}).get("site_score"))
                        if (intel.get("seo") or {}).get("site_score") is not None
                        else None
                    ),
                    "visual_score": (
                        int((intel.get("visual") or {}).get("visual_score"))
                        if (intel.get("visual") or {}).get("visual_score") is not None
                        else None
                    ),
                    "similarity": similarity,
                    "combined_score": combined,
                    "top_reasons": reasons[:5],
                }
            )
        ordered = sort_results(results, self._config)
        return [SearchResult(**item) for item in ordered][: limit]
