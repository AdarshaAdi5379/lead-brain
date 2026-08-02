from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


DIMENSIONS = (
    "discovery_quality",
    "contactability",
    "technical_health",
    "seo_health",
    "content_strength",
    "trust_professionalism",
    "outreach_potential",
)


@dataclass(frozen=True)
class DimensionResult:
    """Score and human-readable reasons for one dimension."""

    name: str
    score: int
    reasons: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "score": self.score, "reasons": list(self.reasons)}


@dataclass(frozen=True)
class ScoringInputs:
    """Every structured signal the deterministic engine may consume.

    All fields are optional: the engine is robust to missing data (failed
    extraction, no crawl, no SEO audit, no fingerprint). It never performs
    network requests or re-crawls; it only reads what the pipeline already
    collected.
    """

    extracted: Optional[dict[str, Any]] = None
    business_name: Optional[str] = None
    category: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    address: Optional[str] = None
    source: Optional[str] = None
    osm_id: Optional[str] = None
    website_url: Optional[str] = None
    fetch_ok: Optional[bool] = None
    last_error: Optional[str] = None
    detections: Optional[list[dict[str, Any]]] = None
    crawl: Optional[dict[str, Any]] = None
    seo_audit: Optional[dict[str, Any]] = None


@dataclass(frozen=True)
class LeadScore:
    """Final deterministic multi-dimensional score for one lead."""

    final_score: int
    priority_label: str
    dimension_scores: dict[str, int]
    dimension_reasons: dict[str, list[str]]
    top_positive_reasons: list[str]
    top_negative_reasons: list[str]
    recommended_outreach_angle: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "final_score": self.final_score,
            "priority_label": self.priority_label,
            "dimension_scores": dict(self.dimension_scores),
            "dimension_reasons": {k: list(v) for k, v in self.dimension_reasons.items()},
            "top_positive_reasons": list(self.top_positive_reasons),
            "top_negative_reasons": list(self.top_negative_reasons),
            "recommended_outreach_angle": self.recommended_outreach_angle,
        }
