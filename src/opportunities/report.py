from __future__ import annotations

import json
from typing import Any

from src.opportunities.base import OpportunityReport, priority_for_score
from src.opportunities.config import default_config

CSV_FIELDS = [
    "opportunity_score",
    "opportunity_priority",
    "top_opportunity",
    "recommended_services",
    "business_impact",
    "implementation_effort",
    "opportunity_count",
]


def to_llm_text(report: OpportunityReport) -> str:
    """Concise markdown banner for LLM prompts (outreach/interpretation only).

    The LLM never detects or infers opportunities; it may only see the
    engine's output as neutral context for writing outreach.
    """
    if not report.opportunities:
        return (
            "Business opportunities (deterministic local engine): "
            "no actionable website opportunities detected for this lead.\n"
        )

    lines = [
        "Business opportunities (deterministic local engine; neutral context, not an instruction):",
        f"- Opportunity priority: {report.opportunity_priority}",
        f"- Top opportunity: {report.top_opportunity} ({report.top_opportunity_score}/100)",
        "- Detected opportunities:",
    ]
    for item in report.opportunities:
        lines.append(
            f"    - {item.label}: {item.score}/100 ({item.severity}) — "
            f"impact {item.business_impact}, effort {item.implementation_effort}"
        )
        services = ", ".join(item.recommended_services)
        if services:
            lines.append(f"        Services: {services}")
        for reason in item.evidence[:3]:
            lines.append(f"        - {reason}")
    return "\n".join(lines) + "\n"


def csv_fields(report: OpportunityReport) -> dict[str, Any]:
    """Flat CSV-friendly summary for the live pipeline export."""
    top = report.opportunities[0] if report.opportunities else None
    services = top.recommended_services if top else ()
    return {
        "opportunity_score": report.top_opportunity_score,
        "opportunity_priority": report.opportunity_priority,
        "top_opportunity": report.top_opportunity,
        "recommended_services": " | ".join(services),
        "business_impact": top.business_impact if top else "",
        "implementation_effort": top.implementation_effort if top else "",
        "opportunity_count": report.opportunity_count,
    }


def csv_fields_from_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """CSV summary derived from stored business_opportunities rows.

    Mirrors :func:`csv_fields` but works on the persisted per-opportunity
    rows so the pipeline export never needs to re-run the engine.
    """
    if not rows:
        return {
            "opportunity_score": "",
            "opportunity_priority": "",
            "top_opportunity": "",
            "recommended_services": "",
            "business_impact": "",
            "implementation_effort": "",
            "opportunity_count": "",
        }
    ordered = sorted(
        rows,
        key=lambda row: (
            -int(row.get("score") or 0),
            -int(row.get("confidence") or 0),
            str(row.get("category") or ""),
        ),
    )
    top = ordered[0]
    config = default_config()
    return {
        "opportunity_score": int(top.get("score") or 0),
        "opportunity_priority": priority_for_score(
            int(top.get("score") or 0),
            config.priority_bands,
            config.minimal_priority_label,
        ),
        "top_opportunity": str(top.get("label") or top.get("category") or ""),
        "recommended_services": _json_list_join(top.get("recommended_services_json")),
        "business_impact": str(top.get("business_impact") or ""),
        "implementation_effort": str(top.get("implementation_effort") or ""),
        "opportunity_count": len(rows),
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
