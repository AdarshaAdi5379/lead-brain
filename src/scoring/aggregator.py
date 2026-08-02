from __future__ import annotations

from typing import Optional

from src.scoring.base import DIMENSIONS, DimensionResult, LeadScore, ScoringInputs
from src.scoring.config import ScoringConfig, default_config
from src.scoring.dimensions import (
    contactability,
    content_strength,
    discovery_quality,
    outreach_potential,
    seo_health,
    technical_health,
    trust_professionalism,
)

# Dimensions whose reasons are only "no signal at all" notes are treated as
# not applicable (e.g. a lead with no website has no SEO/content to assess).
# Their weight is redistributed over the applicable dimensions so the missing
# data cannot dominate the result.
AVAILABILITY_NOTES = {
    "No website to assess",
    "No website to audit",
    "No site content available to assess",
    "No discovery signals available",
    "No contact channels found",
    "No technical signals available",
    "No trust signals available",
    "Limited outreach signals available",
}


def score_site_lead(
    inputs: ScoringInputs,
    config: Optional[ScoringConfig] = None,
) -> LeadScore:
    """Deterministic multi-dimensional lead score.

    Pure function of the supplied signals: no network, no LLM, no DB access.
    The same inputs always produce the same result.
    """
    config = config or default_config()

    base: list[DimensionResult] = [
        discovery_quality(inputs, config),
        contactability(inputs, config),
        technical_health(inputs, config),
        seo_health(inputs, config),
        content_strength(inputs, config),
        trust_professionalism(inputs, config),
    ]
    dimension_scores = {result.name: result.score for result in base}

    outreach = outreach_potential(inputs, config, dimension_scores)
    base.append(outreach)
    dimension_scores[outreach.name] = outreach.score

    dimension_reasons = {result.name: list(result.reasons) for result in base}

    applicable = {result.name for result in base if _is_applicable(result)}
    if not applicable:
        applicable = set(DIMENSIONS)
    weighted = sum(
        config.weights.get(name, 0.0) * dimension_scores[name]
        for name in DIMENSIONS
        if name in applicable
    )
    weight_sum = sum(config.weights.get(name, 0.0) for name in DIMENSIONS if name in applicable)
    final_score = _clamp(round(weighted / weight_sum))
    priority_label = _priority_label(final_score, config)

    positive, negative = _split_reasons(base, dimension_scores)
    positive = positive[: config.top_reasons_max]
    negative = negative[: config.top_reasons_max]
    angle = _outreach_angle(
        final_score=final_score,
        contactable_score=dimension_scores["contactability"],
        seo_score=dimension_scores["seo_health"],
        tech_score=dimension_scores["technical_health"],
        has_website=bool((inputs.website_url or "").strip()),
        positive_reasons=positive,
        max_reasons=config.top_reasons_max,
    )

    return LeadScore(
        final_score=final_score,
        priority_label=priority_label,
        dimension_scores=dict(dimension_scores),
        dimension_reasons=dimension_reasons,
        top_positive_reasons=positive,
        top_negative_reasons=negative,
        recommended_outreach_angle=angle,
    )


def _is_applicable(result: DimensionResult) -> bool:
    return any(reason not in AVAILABILITY_NOTES for reason in result.reasons)


def _clamp(value: int, low: int = 0, high: int = 100) -> int:
    return max(low, min(high, value))


def _priority_label(score: int, config: ScoringConfig) -> str:
    for threshold, label in config.priority_bands:
        if score >= threshold:
            return label
    return "Avoid"


def _split_reasons(
    results: list[DimensionResult],
    dimension_scores: dict[str, int],
) -> tuple[list[str], list[str]]:
    """Deterministic ranking of reasons.

    A reason is positive when it awarded points (contains a "(+N)" marker) or
    its dimension scored >= 35; everything else (missing-signal notes,
    penalties) is negative. Ordering is stable: dimension order, then reason
    order within each dimension.
    """
    positive: list[str] = []
    negative: list[str] = []

    for result in results:
        score = dimension_scores[result.name]
        for reason in result.reasons:
            if "(+)" in reason or score >= 35:
                positive.append(reason)
            else:
                negative.append(reason)

    return positive, negative


def _outreach_angle(
    *,
    final_score: int,
    contactable_score: int,
    seo_score: int,
    tech_score: int,
    has_website: bool,
    positive_reasons: list[str],
    max_reasons: int,
) -> str:
    """Deterministic, template-based outreach recommendation (never LLM)."""
    top = ", ".join(positive_reasons[:max_reasons]) if positive_reasons else "no strong signals"

    if not has_website:
        if contactable_score >= 50:
            return (
                "No website found, but the business is active and contactable. "
                "Propose a simple, modern website that builds on their existing presence."
            )
        return (
            "No website found and limited contact channels. "
            "Try to establish contact first, then position a starter website."
        )

    if seo_score < 50 or tech_score < 50:
        return (
            f"Strong outreach opportunity: the site has clear room for improvement "
            f"(SEO {seo_score}/100, technical {tech_score}/100). "
            "Offer a focused website/SEO review with 2-3 concrete fixes."
        )

    if contactable_score >= 50:
        return (
            f"Reachable business with a healthy site ({final_score}/100 overall). "
            "Position ongoing optimization or maintenance rather than a fix-it pitch."
        )

    return (
        "Average signals overall. "
        "Lead with a no-pressure improvement suggestion and ask about current pain points."
    )
