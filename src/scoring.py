from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional


@dataclass(frozen=True)
class ScoreResult:
    score: int
    priority: str
    recommendation: str
    reasons: list[str]


def _clean(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _clean_lower(value: Any) -> str:
    return _clean(value).lower()


def _clamp_int(value: int, low: int = 0, high: int = 100) -> int:
    return max(low, min(high, value))


def score_lead(extracted: dict[str, Any]) -> ScoreResult:
    """
    PRD v1 scoring (Section 7) with small clarifications:
    - Baseline score = 50, then add/subtract weights, clamp to [0, 100].
    - If no website URL is available: apply only the +40 rule and ignore all other rules.
    - Platform matching is exact match (case-insensitive) after trimming.
    - Unknown complexity/load_speed/platform produce no score change.
    - Recommendation mentions top 2 strongest reasons (by absolute weight).
    """

    baseline = 50
    adjustments: list[tuple[int, str]] = []

    website_url = extracted.get("website_url") or extracted.get("url") or extracted.get("website")
    website_url_clean = _clean(website_url)

    if not website_url_clean:
        adjustments.append((+40, "No website URL found"))
        total = baseline + sum(points for points, _ in adjustments)
        score = _clamp_int(total)
        priority = _priority_for(score)
        reasons = _top_reasons(adjustments, top_n=2)
        return ScoreResult(
            score=score,
            priority=priority,
            recommendation=_recommendation(priority, reasons),
            reasons=reasons,
        )

    platform = _clean_lower(extracted.get("platform"))
    complexity = _clean_lower(extracted.get("complexity"))
    load_speed = _clean_lower(extracted.get("load_speed"))
    phone = _clean(extracted.get("phone"))
    email = _clean(extracted.get("email"))

    # Positive signals
    if platform in {"wix", "weebly", "squarespace", "html", "basic html"}:
        adjustments.append((+30, f"Basic platform ({platform})"))

    if load_speed == "slow":
        adjustments.append((+20, "Slow load speed"))

    if not phone:
        adjustments.append((+15, "Phone missing"))
    else:
        adjustments.append((-10, "Phone exists"))

    if not email:
        adjustments.append((+15, "Email missing"))
    else:
        adjustments.append((-10, "Email exists"))

    if platform == "wordpress" and complexity == "basic":
        adjustments.append((+10, "Basic WordPress site"))

    # Negative signals
    if platform in {"shopify", "custom react", "react"}:
        adjustments.append((-20, f"Modern/complex platform ({platform})"))

    if complexity in {"complex", "large"}:
        adjustments.append((-30, f"High complexity ({complexity})"))

    total = baseline + sum(points for points, _ in adjustments)
    score = _clamp_int(total)
    priority = _priority_for(score)
    reasons = _top_reasons(adjustments, top_n=2)

    return ScoreResult(
        score=score,
        priority=priority,
        recommendation=_recommendation(priority, reasons),
        reasons=reasons,
    )


def _priority_for(score: int) -> str:
    if score >= 70:
        return "Hot"
    if score >= 50:
        return "Warm"
    if score >= 30:
        return "Cold"
    return "Avoid"


def _top_reasons(adjustments: list[tuple[int, str]], top_n: int) -> list[str]:
    ordered = sorted(adjustments, key=lambda item: (abs(item[0]), item[0]), reverse=True)
    return [f"{reason} ({points:+d})" for points, reason in ordered[:top_n]]


def _recommendation(priority: str, reasons: list[str]) -> str:
    reasons_text = ", ".join(reasons) if reasons else "No strong signals detected"

    if priority == "Hot":
        return f"Contact immediately. Top signals: {reasons_text}."
    if priority == "Warm":
        return f"Contact within the week. Top signals: {reasons_text}."
    if priority == "Cold":
        return f"Low priority; consider nurturing. Top signals: {reasons_text}."
    return f"Avoid spending time on this lead. Top signals: {reasons_text}."

