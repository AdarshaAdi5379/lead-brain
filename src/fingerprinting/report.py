from __future__ import annotations

from typing import Any, Optional

from src.fingerprinting.base import CATEGORY_LABELS, Detection
from src.fingerprinting.detector import FingerprintResult


def detections_by_category(detections: tuple[Detection, ...]) -> dict[str, list[Detection]]:
    """Group detections by category, preserving catalogue label order."""
    ordered: dict[str, list[Detection]] = {}
    for detection in detections:
        ordered.setdefault(detection.category, []).append(detection)
    return ordered


def to_dict(result: FingerprintResult, *, site_url: str | None = None) -> dict[str, Any]:
    """Structured report dict (sorted by confidence, then name)."""
    detections = sorted(
        result.detections, key=lambda d: (-d.confidence, CATEGORY_LABELS.get(d.category, d.category), d.name)
    )
    return {
        "site_url": site_url or result.site_url,
        "technologies": [d.to_dict() for d in detections],
        "count": len(detections),
    }


def to_llm_text(result: FingerprintResult, *, max_items: int = 12) -> str:
    """Markdown summary for the LLM prompt (empty section string if no detections).

    The LLM is never asked to detect technology — it just consumes this as
    neutral context alongside the scraped site content.
    """
    detections = sorted(
        result.detections, key=lambda d: (-d.confidence, CATEGORY_LABELS.get(d.category, d.category), d.name)
    )[:max_items]
    if not detections:
        return "Detected technologies:\n- (none detected; rely on site content and your own judgement)\n"

    lines = ["Detected technologies (guessed from page HTML/headers; trust your own reading):"]
    current_category: Optional[str] = None
    for detection in detections:
        label = CATEGORY_LABELS.get(detection.category, detection.category)
        if label != current_category:
            current_category = label
            lines.append(f"- {label}:")
        confidence = f"{detection.confidence}%"
        hints = ", ".join(detection.evidence[:3]) or "signal matched"
        lines.append(f"    - {detection.name} ({confidence}) — {hints}")
    return "\n".join(lines) + "\n"


def summary_csv_fields(result: FingerprintResult) -> dict[str, Any]:
    """Flat CSV-friendly summary: cms, frontend_framework, hosting, analytics, confidence_summary."""
    top = sorted(result.detections, key=lambda d: -d.confidence)
    by_cat: dict[str, list[str]] = {}
    for d in top:
        by_cat.setdefault(d.category, []).append(d.name)

    confidence_summary = "; ".join(f"{d.name} ({d.confidence}%)" for d in top[:6]) if top else ""

    return {
        "cms": ", ".join(by_cat.get("cms", [])),
        "frontend_technology": ", ".join(by_cat.get("frontend", [])),
        "backend_technology": ", ".join(by_cat.get("backend", [])),
        "hosting_cdn": ", ".join(by_cat.get("hosting", [])),
        "analytics": ", ".join(by_cat.get("analytics", [])),
        "confidence_summary": confidence_summary,
    }