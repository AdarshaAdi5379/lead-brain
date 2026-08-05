from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from src.scoring.base import LeadScore, ScoringInputs

CATEGORY_LABELS = {
    "website_redesign": "Website Redesign",
    "seo_improvement": "SEO Improvement",
    "performance_optimization": "Performance Optimization",
    "accessibility_improvement": "Accessibility Improvement",
    "content_improvement": "Content Improvement",
    "brand_refresh": "Brand Refresh",
    "technical_modernization": "Technical Modernization",
    "mobile_optimization": "Mobile Optimization",
    "analytics_setup": "Analytics Setup",
    "security_improvement": "Security Improvement",
    "local_seo": "Local SEO",
    "contact_funnel_improvement": "Contact Funnel Improvement",
    "conversion_optimization": "Conversion Optimization",
    "hosting_upgrade": "Hosting Upgrade",
    "ecommerce_optimization": "E-commerce Optimization",
    "maintenance_opportunity": "Maintenance Opportunity",
}

BUSINESS_IMPACTS = ("Low", "Medium", "High", "Very High")
EFFORTS = ("Easy", "Medium", "Hard")


@dataclass(frozen=True)
class Opportunity:
    """One deterministic business opportunity detected for a lead.

    Pure output of the local engine: the score is a 0-100 signal strength,
    the severity is derived from the configured score bands, and every
    piece of evidence is a human-readable reason computed from collected
    signals. The LLM never creates or modifies opportunities; it may only
    read them via the report banner.
    """

    category: str
    label: str
    score: int
    severity: str
    confidence: int
    evidence: tuple[str, ...] = ()
    business_impact: str = "Medium"
    implementation_effort: str = "Medium"
    recommended_services: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "label": self.label,
            "score": self.score,
            "severity": self.severity,
            "confidence": self.confidence,
            "evidence": list(self.evidence),
            "business_impact": self.business_impact,
            "implementation_effort": self.implementation_effort,
            "recommended_services": list(self.recommended_services),
        }


@dataclass(frozen=True)
class OpportunityReport:
    """Lead-level summary over all detected opportunities.

    ``contact`` is a small, input-derived contact context (website, phone,
    email, address, social URLs, primary contact / best contact method)
    attached for reporting only — it never influences the opportunity score.
    """

    opportunities: tuple[Opportunity, ...] = ()
    opportunity_priority: str = "Minimal Opportunity"
    top_opportunity: str = ""
    top_opportunity_score: int = 0
    opportunity_count: int = 0
    contact: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "opportunities": [item.to_dict() for item in self.opportunities],
            "opportunity_priority": self.opportunity_priority,
            "top_opportunity": self.top_opportunity,
            "top_opportunity_score": self.top_opportunity_score,
            "opportunity_count": self.opportunity_count,
            "contact": dict(self.contact),
        }


def severity_for_score(score: int, bands: tuple[tuple[int, str], ...]) -> str:
    """Map a 0-100 score to a severity label using the configured bands."""
    for threshold, label in bands:
        if score >= threshold:
            return label
    return "Ignore"


def priority_for_score(score: int, bands: tuple[tuple[int, str], ...], fallback: str) -> str:
    for threshold, label in bands:
        if score >= threshold:
            return label
    return fallback
