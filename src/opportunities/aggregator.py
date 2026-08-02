from __future__ import annotations

from typing import Optional

from src.opportunities.base import Opportunity, OpportunityReport, priority_for_score
from src.opportunities.config import OpportunityConfig, default_config
from src.opportunities.registry import OPPORTUNITY_DETECTORS
from src.scoring.base import LeadScore, ScoringInputs


def detect_opportunities(
    signals: ScoringInputs,
    lead_score: Optional[LeadScore] = None,
    config: Optional[OpportunityConfig] = None,
) -> OpportunityReport:
    """Deterministic business opportunity detection for one lead.

    Pure function of the supplied signals: no network, no LLM, no DB access.
    The same inputs always produce the same report.
    """
    config = config or default_config()

    if not (signals.website_url or "").strip():
        return OpportunityReport()

    opportunities: list[Opportunity] = []
    for category, detector in OPPORTUNITY_DETECTORS:
        try:
            item = detector(signals, lead_score, config)
        except Exception:  # a broken detector must never break the engine
            item = None
        if item is not None:
            opportunities.append(item)

    # Deterministic ordering: highest score first, then confidence, then
    # category name (stable and reproducible).
    opportunities.sort(
        key=lambda item: (-item.score, -item.confidence, item.category)
    )
    report = OpportunityReport(opportunities=tuple(opportunities))

    top = opportunities[0] if opportunities else None
    if top is None:
        return OpportunityReport()
    priority = priority_for_score(
        top.score,
        config.priority_bands,
        config.minimal_priority_label,
    )
    return OpportunityReport(
        opportunities=tuple(opportunities),
        opportunity_priority=priority,
        top_opportunity=top.label,
        top_opportunity_score=top.score,
        opportunity_count=len(opportunities),
    )
