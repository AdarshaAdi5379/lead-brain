from __future__ import annotations

from src.opportunities.aggregator import detect_opportunities
from src.opportunities.base import (
    CATEGORY_LABELS,
    Opportunity,
    OpportunityReport,
    severity_for_score,
)
from src.opportunities.config import OpportunityConfig, default_config

__all__ = [
    "CATEGORY_LABELS",
    "Opportunity",
    "OpportunityConfig",
    "OpportunityReport",
    "default_config",
    "detect_opportunities",
    "severity_for_score",
]
