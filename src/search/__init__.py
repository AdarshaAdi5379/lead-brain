from __future__ import annotations

from src.search.cache import document_hash, embedding_hash, should_reindex
from src.search.config import SearchConfig, from_settings
from src.search.embedding import (
    Embedder,
    EmbeddingUnavailableError,
    HashingEmbedder,
    SentenceTransformersEmbedder,
    get_embedder,
)
from src.search.index import SearchDocument, build_lead_document
from src.search.query import SearchError, SearchQuery, validate_filters, validate_query
from src.search.ranking import RankInput, combined_score, recency_score
from src.search.search_service import IndexStats, SearchResult, SearchService
from src.search.summarizer import build_context, context_to_text
from src.search.vector_store import StoredHit, VectorStore, get_vector_store

__all__ = [
    "Embedder",
    "EmbeddingUnavailableError",
    "HashingEmbedder",
    "IndexStats",
    "RankInput",
    "SearchConfig",
    "SearchDocument",
    "SearchError",
    "SearchQuery",
    "SearchResult",
    "SearchService",
    "SentenceTransformersEmbedder",
    "StoredHit",
    "VectorStore",
    "build_context",
    "build_lead_document",
    "combined_score",
    "context_to_text",
    "document_hash",
    "embedding_hash",
    "from_settings",
    "get_embedder",
    "get_vector_store",
    "recency_score",
    "should_reindex",
    "validate_filters",
    "validate_query",
]
