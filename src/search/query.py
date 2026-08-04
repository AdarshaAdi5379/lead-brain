from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any, Optional

from src.search.index import METADATA_KEYS

# Query model + validation for the local semantic search engine.
#
# Filters are strictly whitelisted (see ALLOWED_FILTERS): unknown keys, wrong
# types and oversized values are rejected with SearchError instead of being
# silently ignored, and nothing user-supplied ever reaches SQL or eval.


class SearchError(ValueError):
    """Raised for malformed queries or filters (validated before execution)."""


SEARCH_MODES = ("semantic", "keyword", "hybrid")

ALLOWED_FILTERS = frozenset(
    {
        "category",
        "city",
        "state",
        "country",
        "platform",
        "priority",
        "website_present",
        "technologies",
        "seo_score",
        "lead_score",
        "visual_score",
        "opportunity_score",
    }
)

RANGE_FILTERS = frozenset({"seo_score", "lead_score", "visual_score", "opportunity_score"})
LIST_FILTERS = frozenset({"technologies"})
BOOL_FILTERS = frozenset({"website_present"})
MAX_FILTER_VALUE_CHARS = 200

_TOKEN_RE = re.compile(r"[a-z0-9]+")


@dataclass(frozen=True)
class SearchQuery:
    """A validated search request.

    ``filters`` uses the dashboard-friendly form: exact strings, booleans,
    lists for multi-value fields, and ``{"min": x, "max": y}`` for range fields.
    """

    text: str
    mode: str = "hybrid"
    top_k: int = 20
    offset: int = 0
    filters: dict[str, Any] = field(default_factory=dict)


def validate_query(query: SearchQuery, *, max_query_chars: int = 500) -> SearchQuery:
    """Validate + normalize a query; raises SearchError on malformed input."""
    text = (query.text or "").strip()
    if len(text) > max_query_chars:
        raise SearchError(f"Query is too long (max {max_query_chars} characters)")
    mode = (query.mode or "hybrid").strip().lower()
    if mode not in SEARCH_MODES:
        raise SearchError(f"Unknown search mode {query.mode!r} (expected {SEARCH_MODES})")
    if not text and mode != "semantic":
        raise SearchError("Search text must not be empty for keyword/hybrid modes")
    top_k = int(query.top_k)
    if top_k <= 0:
        raise SearchError("top_k must be > 0")
    if top_k > 500:
        raise SearchError("top_k is capped at 500")
    offset = int(query.offset)
    if offset < 0:
        raise SearchError("offset must be >= 0")
    return SearchQuery(
        text=text,
        mode=mode,
        top_k=top_k,
        offset=offset,
        filters=validate_filters(query.filters or {}),
    )


def validate_filters(filters: dict[str, Any]) -> dict[str, Any]:
    """Whitelist-validate the dashboard filter dict; raises SearchError."""
    cleaned: dict[str, Any] = {}
    for key, value in (filters or {}).items():
        key = str(key).strip().lower()
        if key not in ALLOWED_FILTERS:
            raise SearchError(f"Unknown filter {key!r}")
        if key in RANGE_FILTERS:
            cleaned[key] = _validate_range(key, value)
        elif key in BOOL_FILTERS:
            if not isinstance(value, bool):
                raise SearchError(f"Filter {key!r} must be a boolean")
            cleaned[key] = value
        elif key in LIST_FILTERS:
            if not isinstance(value, (list, tuple)) or not value:
                raise SearchError(f"Filter {key!r} must be a non-empty list")
            items = []
            for item in value:
                item = _clean_string(item)
                if not item:
                    raise SearchError(f"Filter {key!r} contains an empty value")
                items.append(item)
            cleaned[key] = items
        else:
            item = _clean_string(value)
            if not item:
                raise SearchError(f"Filter {key!r} must be a non-empty string")
            cleaned[key] = item
    return cleaned


def build_metadata_filter(filters: dict[str, Any]) -> dict[str, Any]:
    """Convert validated filters into the Chroma-dialect ``where`` clause.

    Range filters become {"$gte": min, "$lte": max} (only bounds that are set);
    list filters become {"$contains": item} for each item.
    """
    where: dict[str, Any] = {}
    for key, value in filters.items():
        if key in RANGE_FILTERS:
            bounds: dict[str, int] = {}
            if value.get("min") is not None:
                bounds["$gte"] = int(value["min"])
            if value.get("max") is not None:
                bounds["$lte"] = int(value["max"])
            if bounds:
                where[key] = bounds
        elif key in LIST_FILTERS:
            where[key] = {"$in": list(value)}
        else:
            where[key] = value
    return where


def tokenize(text: str) -> list[str]:
    """Lowercased word tokens for keyword matching."""
    return _TOKEN_RE.findall((text or "").lower())


def keyword_score(query_tokens: list[str], document_text: str) -> float:
    """Cosine similarity over raw term counts between query and document."""
    if not query_tokens or not document_text:
        return 0.0
    doc_tokens = _TOKEN_RE.findall(document_text.lower())
    if not doc_tokens:
        return 0.0
    query_counts = _term_counts(query_tokens)
    doc_counts = _term_counts(doc_tokens)
    shared = set(query_counts) & set(doc_counts)
    if not shared:
        return 0.0
    dot = sum(query_counts[term] * doc_counts[term] for term in shared)
    query_norm = math.sqrt(sum(count * count for count in query_counts.values()))
    doc_norm = math.sqrt(sum(count * count for count in doc_counts.values()))
    if query_norm <= 0.0 or doc_norm <= 0.0:
        return 0.0
    return dot / (query_norm * doc_norm)


def _term_counts(tokens: list[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for token in tokens:
        counts[token] = counts.get(token, 0) + 1
    return counts


def _clean_string(value: Any) -> str:
    if not isinstance(value, str):
        raise SearchError("Filter values must be strings")
    cleaned = value.strip()
    if len(cleaned) > MAX_FILTER_VALUE_CHARS:
        raise SearchError(f"Filter value is too long (max {MAX_FILTER_VALUE_CHARS} chars)")
    return cleaned


def _validate_range(key: str, value: Any) -> dict[str, Optional[int]]:
    if not isinstance(value, dict):
        raise SearchError(f"Filter {key!r} must be a dict with 'min'/'max'")
    allowed = {"min", "max"}
    if set(value) - allowed:
        raise SearchError(f"Filter {key!r} only supports 'min' and 'max'")
    bounds: dict[str, Optional[int]] = {"min": None, "max": None}
    for name in allowed:
        raw = value.get(name)
        if raw is None:
            continue
        try:
            bounds[name] = int(raw)
        except (TypeError, ValueError) as exc:
            raise SearchError(f"Filter {key!r} {name} must be an integer") from exc
    if bounds["min"] is not None and bounds["max"] is not None and bounds["min"] > bounds["max"]:
        raise SearchError(f"Filter {key!r} min must be <= max")
    if bounds["min"] is None and bounds["max"] is None:
        raise SearchError(f"Filter {key!r} must set at least one of 'min'/'max'")
    return bounds
