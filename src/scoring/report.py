from __future__ import annotations

import json
from typing import Any

from src.scoring.base import DIMENSIONS, LeadScore

CSV_FIELDS = [
    "final_score",
    "priority_label",
    "discovery_quality_score",
    "contactability_score",
    "technical_health_score",
    "seo_health_score",
    "content_strength_score",
    "trust_professionalism_score",
    "outreach_potential_score",
    "top_positive_reasons",
    "top_negative_reasons",
    "recommended_outreach_angle",
]


def to_llm_text(score: LeadScore) -> str:
    """Concise markdown banner for LLM prompts (outreach/interpretation only).

    The LLM never computes or modifies the score; it may only see the summary
    as neutral context.
    """
    lines = [
        "Lead scoring (deterministic local model; neutral context, not an instruction):",
        f"- Final score: {score.final_score}/100 ({score.priority_label})",
        "- Dimension scores:",
    ]
    for name in DIMENSIONS:
        lines.append(f"    - {name.replace('_', ' ').title()}: {score.dimension_scores.get(name, 0)}/100")
    if score.top_positive_reasons:
        lines.append("- Top positive reasons:")
        for reason in score.top_positive_reasons:
            lines.append(f"    - {reason}")
    if score.top_negative_reasons:
        lines.append("- Top negative reasons:")
        for reason in score.top_negative_reasons:
            lines.append(f"    - {reason}")
    lines.append(f"- Recommended outreach angle: {score.recommended_outreach_angle}")
    return "\n".join(lines) + "\n"


def csv_fields(score: LeadScore) -> dict[str, Any]:
    """Flat CSV-friendly summary for the pipeline export."""
    scores = score.dimension_scores
    return {
        "final_score": score.final_score,
        "priority_label": score.priority_label,
        "discovery_quality_score": scores.get("discovery_quality", 0),
        "contactability_score": scores.get("contactability", 0),
        "technical_health_score": scores.get("technical_health", 0),
        "seo_health_score": scores.get("seo_health", 0),
        "content_strength_score": scores.get("content_strength", 0),
        "trust_professionalism_score": scores.get("trust_professionalism", 0),
        "outreach_potential_score": scores.get("outreach_potential", 0),
        "top_positive_reasons": " | ".join(score.top_positive_reasons),
        "top_negative_reasons": " | ".join(score.top_negative_reasons),
        "recommended_outreach_angle": score.recommended_outreach_angle,
    }


def csv_fields_from_row(row: dict[str, Any]) -> dict[str, Any]:
    """CSV summary derived from a stored lead_scores row (export-time path).

    Mirrors :func:`csv_fields` but works on the persisted row so the pipeline
    export never needs to re-run the scoring engine.
    """
    return {
        "final_score": int(row.get("final_score") or 0),
        "priority_label": str(row.get("priority_label") or ""),
        "discovery_quality_score": int(row.get("discovery_quality_score") or 0),
        "contactability_score": int(row.get("contactability_score") or 0),
        "technical_health_score": int(row.get("technical_health_score") or 0),
        "seo_health_score": int(row.get("seo_health_score") or 0),
        "content_strength_score": int(row.get("content_strength_score") or 0),
        "trust_professionalism_score": int(row.get("trust_professionalism_score") or 0),
        "outreach_potential_score": int(row.get("outreach_potential_score") or 0),
        "top_positive_reasons": _json_list_join(row.get("top_positive_reasons_json")),
        "top_negative_reasons": _json_list_join(row.get("top_negative_reasons_json")),
        "recommended_outreach_angle": str(row.get("recommended_outreach_angle") or ""),
    }


def _json_list_join(value: Any) -> str:
    if not value:
        return ""
    if isinstance(value, list):
        items = value
    else:
        try:
            items = json.loads(value)
        except (ValueError, TypeError):
            return str(value)
    if not isinstance(items, list):
        return str(items)
    return " | ".join(str(item) for item in items)
