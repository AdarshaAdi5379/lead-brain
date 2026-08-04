from __future__ import annotations

from typing import Any, Optional

# AI Context Builder: a reusable, structured summary of one lead's collected
# intelligence (business, technology, SEO, visual, opportunities, scoring).
#
# Pure functions over the stored intelligence dicts — no network, no LLM. This
# context is designed to power a future AI chat / outreach assistant, and is
# also used by the dashboard detail view.


def build_context(intel: dict[str, Any]) -> Optional[dict[str, Any]]:
    """Structured context for one lead (None when the lead row is missing)."""
    lead = intel.get("lead")
    if not lead:
        return None
    score = intel.get("score")
    seo = intel.get("seo")
    visual = intel.get("visual")
    opportunities = intel.get("opportunities") or []
    detections = intel.get("detections") or []

    return {
        "business": {
            "business_name": lead.get("business_name"),
            "category": lead.get("category"),
            "city": lead.get("city"),
            "state": lead.get("state"),
            "country": lead.get("country"),
            "address": lead.get("address"),
            "website_url": lead.get("website_url"),
            "phone": lead.get("phone"),
            "email": lead.get("email"),
            "source": lead.get("source"),
        },
        "technology": {
            "platform": lead.get("platform"),
            "complexity": lead.get("complexity"),
            "load_speed": lead.get("load_speed"),
            "detections": [
                {
                    "name": detection.get("technology_name"),
                    "category": detection.get("category"),
                    "confidence": detection.get("confidence"),
                }
                for detection in detections
            ],
        },
        "seo": _seo_summary(seo),
        "visual": _visual_summary(visual),
        "opportunities": {
            "count": len(opportunities),
            "top_opportunity": opportunities[0].get("label") if opportunities else None,
            "opportunity_score": max(
                (int(item.get("score") or 0) for item in opportunities), default=0
            ),
            "items": [
                {
                    "label": item.get("label"),
                    "category": item.get("category"),
                    "score": item.get("score"),
                    "severity": item.get("severity"),
                    "business_impact": item.get("business_impact"),
                    "implementation_effort": item.get("implementation_effort"),
                    "evidence": item.get("evidence") or [],
                    "recommended_services": item.get("recommended_services") or [],
                }
                for item in opportunities
            ],
        },
        "scoring": _scoring_summary(score),
    }


def context_to_text(context: dict[str, Any]) -> str:
    """Markdown rendering of the context (neutral, LLM-friendly)."""
    lines: list[str] = []
    business = context.get("business") or {}
    title = business.get("business_name") or "Business"
    lines.append(f"# {title}")
    if business.get("category"):
        lines.append(f"- Category: {business['category']}")
    location = ", ".join(
        part
        for part in (
            business.get("city"),
            business.get("state"),
            business.get("country"),
        )
        if part
    )
    if location:
        lines.append(f"- Location: {location}")
    if business.get("phone"):
        lines.append(f"- Phone: {business['phone']}")
    if business.get("email"):
        lines.append(f"- Email: {business['email']}")
    if business.get("website_url"):
        lines.append(f"- Website: {business['website_url']}")

    technology = context.get("technology") or {}
    tech_parts = [
        part
        for part in (
            technology.get("platform"),
            technology.get("complexity"),
            technology.get("load_speed"),
        )
        if part and part != "unknown"
    ]
    tech_parts += [
        f"{item['name']} ({item.get('category')}, {item.get('confidence')}%)"
        for item in technology.get("detections") or []
    ]
    if tech_parts:
        lines.append("## Technology")
        lines.append(", ".join(dict.fromkeys(tech_parts)))

    seo = context.get("seo") or {}
    if seo.get("site_score") is not None:
        lines.append("## SEO")
        lines.append(
            f"- Score: {seo['site_score']}/100 ({seo.get('overall_health') or 'unknown'})"
        )
        for issue in (seo.get("top_issues") or [])[:5]:
            lines.append(f"- {issue}")

    visual = context.get("visual") or {}
    if visual.get("visual_score") is not None:
        lines.append("## Visual")
        lines.append(
            f"- Score: {visual['visual_score']}/100 ({visual.get('visual_health_label') or 'unknown'})"
        )
        if visual.get("summary"):
            lines.append(f"- {visual['summary']}")

    opportunities = context.get("opportunities") or {}
    items = opportunities.get("items") or []
    if items:
        lines.append("## Opportunities")
        lines.append(
            f"- Priority: {opportunities.get('opportunity_score')}/100"
            f" ({len(items)} detected)"
        )
        for item in items[:5]:
            lines.append(f"- {item.get('label')} ({item.get('score')}/100)")
            for evidence in (item.get("evidence") or [])[:2]:
                lines.append(f"    - {evidence}")

    scoring = context.get("scoring") or {}
    if scoring.get("final_score") is not None:
        lines.append("## Scoring")
        lines.append(
            f"- Final: {scoring['final_score']}/100 ({scoring.get('priority_label') or 'unknown'})"
        )
        for reason in (scoring.get("top_positive_reasons") or [])[:3]:
            lines.append(f"+ {reason}")
        for reason in (scoring.get("top_negative_reasons") or [])[:3]:
            lines.append(f"- {reason}")
        if scoring.get("recommended_outreach_angle"):
            lines.append(f"- Outreach angle: {scoring['recommended_outreach_angle']}")

    return "\n".join(lines)


def _seo_summary(seo: Optional[dict[str, Any]]) -> dict[str, Any]:
    if not seo:
        return {}
    return {
        "site_score": seo.get("site_score"),
        "overall_health": seo.get("overall_health"),
        "total_pages_audited": seo.get("total_pages_audited"),
        "top_issues": [
            str(issue.get("reason")) if isinstance(issue, dict) else str(issue)
            for issue in (seo.get("severity_summary") or [])
        ],
    }


def _visual_summary(visual: Optional[dict[str, Any]]) -> dict[str, Any]:
    if not visual:
        return {}
    return {
        "visual_score": visual.get("visual_score"),
        "visual_health_label": visual.get("visual_health_label"),
        "summary": visual.get("summary"),
        "total_pages_audited": visual.get("total_pages_audited"),
    }


def _scoring_summary(score: Optional[dict[str, Any]]) -> dict[str, Any]:
    if not score:
        return {}
    return {
        "final_score": score.get("final_score"),
        "priority_label": score.get("priority_label"),
        "dimension_scores": {
            name: score.get(name)
            for name in (
                "discovery_quality_score",
                "contactability_score",
                "technical_health_score",
                "seo_health_score",
                "content_strength_score",
                "trust_professionalism_score",
                "outreach_potential_score",
                "visual_presentation_score",
            )
        },
        "top_positive_reasons": score.get("top_positive_reasons") or [],
        "top_negative_reasons": score.get("top_negative_reasons") or [],
        "recommended_outreach_angle": score.get("recommended_outreach_angle"),
    }
