from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from src.search.config import SearchConfig, rank_weights

# Deterministic final ranking for search results.
#
# final = w1*similarity + w2*lead_score/100 + w3*opportunity_score/100 +
#         w4*recency
# Weights come from SearchConfig (normalized to sum to 1) and every component
# is clamped to 0..1, so the result is a stable, explainable 0..1 score.
# Missing scores count as 0 (unscored leads rank lower, never crash).

_RECENCY_HALF_LIFE_DAYS = 365.0


@dataclass(frozen=True)
class RankInput:
    """Relevance + quality signals used for the combined ranking."""

    similarity: float
    lead_score: Optional[int] = None
    opportunity_score: Optional[int] = None
    recency: float = 0.0


def combined_score(inputs: RankInput, config: SearchConfig) -> float:
    """Combine vector similarity, lead quality and recency into one score."""
    similarity = _clamp01(inputs.similarity)
    lead = _clamp01((inputs.lead_score or 0) / 100.0)
    opportunity = _clamp01((inputs.opportunity_score or 0) / 100.0)
    recency = _clamp01(inputs.recency)
    weights = rank_weights(config)
    return (
        weights[0] * similarity
        + weights[1] * lead
        + weights[2] * opportunity
        + weights[3] * recency
    )


def recency_score(updated_at: Optional[str]) -> float:
    """Recency in 0..1: 1 for today, decaying to ~0 after a year."""
    if not updated_at:
        return 0.0
    parsed = _parse_timestamp(updated_at)
    if parsed is None:
        return 0.0
    age_days = max(0.0, (datetime.now(timezone.utc) - parsed).total_seconds() / 86400.0)
    return 1.0 / (1.0 + age_days / _RECENCY_HALF_LIFE_DAYS)


def sort_results(
    results: list[dict[str, Any]], config: SearchConfig
) -> list[dict[str, Any]]:
    """Stable deterministic sort by combined score, then similarity, then id."""
    return sorted(
        results,
        key=lambda item: (
            -float(item.get("combined_score") or 0.0),
            -float(item.get("similarity") or 0.0),
            int(item.get("lead_id") or 0),
        ),
    )


def _parse_timestamp(value: str) -> Optional[datetime]:
    text = value.strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))
