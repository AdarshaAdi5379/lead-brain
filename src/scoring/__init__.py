from __future__ import annotations

from src.scoring.aggregator import score_site_lead
from src.scoring.base import DimensionResult, LeadScore, ScoringInputs
from src.scoring.config import ScoringConfig, default_config
from src.scoring.legacy import ScoreResult, score_lead

__all__ = [
    "DimensionResult",
    "LeadScore",
    "ScoreResult",
    "ScoringConfig",
    "ScoringInputs",
    "default_config",
    "score_lead",
    "score_site_lead",
]
