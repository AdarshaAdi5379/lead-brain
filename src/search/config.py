from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import src.settings as settings_module
from src.settings import PROJECT_ROOT


@dataclass(frozen=True)
class SearchConfig:
    """Tunables for the local semantic search engine.

    Follows the repo convention of engine tunables living in a config object
    built from environment-backed settings (see ``src/visual/config.py``).
    """

    # Master switch: when off the pipeline never indexes and search is disabled.
    enabled: bool = True
    # Embedder backend: "auto" | "hash" | "sentence".
    embedder: str = "auto"
    # sentence-transformers model (and fallback when the primary fails to load).
    embedding_model: str = "all-MiniLM-L6-v2"
    embedding_model_fallback: str = "bge-small-en-v1.5"
    embedding_device: str = "cpu"
    # Feature-space size for the deterministic hashing embedder.
    hash_dimensions: int = 512
    # Vector store backend: "auto" | "sqlite" | "chroma".
    vector_store: str = "auto"
    chroma_dir: Path = field(default_factory=lambda: PROJECT_ROOT / "data" / "chroma")
    # Embedding batch size (both backends).
    batch_size: int = 32
    # Default result count.
    default_top_k: int = 20
    # Share of semantic similarity in hybrid search (0-1).
    hybrid_weight: float = 0.7
    # Final ranking weights (must sum to 1): similarity, lead, opportunity, recency.
    rank_weight_similarity: float = 0.5
    rank_weight_lead: float = 0.25
    rank_weight_opportunity: float = 0.15
    rank_weight_recency: float = 0.10
    # Hard cap on raw user-query length (safety).
    max_query_chars: int = 500


def from_settings(module: Any = settings_module) -> SearchConfig:
    """Build a SearchConfig from the environment-backed settings module."""
    return SearchConfig(
        enabled=bool(getattr(module, "SEARCH_ENABLED", True)),
        embedder=str(getattr(module, "SEARCH_EMBEDDER", "auto")).strip().lower(),
        embedding_model=str(
            getattr(module, "SEARCH_EMBEDDING_MODEL", "all-MiniLM-L6-v2")
        ),
        embedding_model_fallback=str(
            getattr(module, "SEARCH_EMBEDDING_MODEL_FALLBACK", "bge-small-en-v1.5")
        ),
        embedding_device=str(getattr(module, "SEARCH_EMBEDDING_DEVICE", "cpu")),
        hash_dimensions=int(getattr(module, "SEARCH_HASH_DIMENSIONS", 512)),
        vector_store=str(getattr(module, "SEARCH_VECTOR_STORE", "auto")).strip().lower(),
        chroma_dir=Path(getattr(module, "SEARCH_CHROMA_DIR", PROJECT_ROOT / "data" / "chroma")),
        batch_size=int(getattr(module, "SEARCH_BATCH_SIZE", 32)),
        default_top_k=int(getattr(module, "SEARCH_TOP_K", 20)),
        hybrid_weight=float(getattr(module, "SEARCH_HYBRID_WEIGHT", 0.7)),
        rank_weight_similarity=float(
            getattr(module, "SEARCH_RANK_WEIGHT_SIMILARITY", 0.5)
        ),
        rank_weight_lead=float(getattr(module, "SEARCH_RANK_WEIGHT_LEAD", 0.25)),
        rank_weight_opportunity=float(
            getattr(module, "SEARCH_RANK_WEIGHT_OPPORTUNITY", 0.15)
        ),
        rank_weight_recency=float(getattr(module, "SEARCH_RANK_WEIGHT_RECENCY", 0.10)),
        max_query_chars=int(getattr(module, "SEARCH_MAX_QUERY_CHARS", 500)),
    )


def rank_weights(config: SearchConfig) -> tuple[float, float, float, float]:
    """Normalized (similarity, lead, opportunity, recency) weights summing to 1."""
    total = (
        config.rank_weight_similarity
        + config.rank_weight_lead
        + config.rank_weight_opportunity
        + config.rank_weight_recency
    )
    if total <= 0:
        return (0.5, 0.25, 0.15, 0.10)
    scale = 1.0 / total
    return (
        config.rank_weight_similarity * scale,
        config.rank_weight_lead * scale,
        config.rank_weight_opportunity * scale,
        config.rank_weight_recency * scale,
    )
