from __future__ import annotations

from typing import Any, Optional

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
    The same inputs always produce the same report. The attached contact
    context is derived from the same inputs for reporting only — it never
    affects the opportunity score.
    """
    config = config or default_config()

    if not (signals.website_url or "").strip():
        return OpportunityReport()

    contact = _contact_context(signals)
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
    report = OpportunityReport(opportunities=tuple(opportunities), contact=contact)

    top = opportunities[0] if opportunities else None
    if top is None:
        return report
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
        contact=contact,
    )


def _contact_context(signals: ScoringInputs) -> dict[str, Any]:
    """Compact, deterministic contact context attached to the report.

    Reads only what the pipeline already collected (extraction + crawl); a
    missing piece is simply omitted, never guessed.
    """
    extracted = signals.extracted or {}
    phone = str(extracted.get("phone") or "").strip()
    email = str(extracted.get("email") or "").strip()
    social = [
        str(url)
        for url in ((signals.crawl or {}).get("social_urls") or [])
        if str(url).strip()
    ]
    contact: dict[str, Any] = {}
    website = str(signals.website_url or "").strip()
    if website:
        contact["website"] = website
    if phone:
        contact["phone"] = phone
    if email:
        contact["email"] = email
    if (signals.address or "").strip():
        contact["address"] = str(signals.address).strip()
    if social:
        contact["social_urls"] = social
    if email or phone:
        contact["primary_contact"] = email or phone
        contact["best_contact_method"] = "email" if email else "phone"
    return contact
