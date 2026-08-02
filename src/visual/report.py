from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from src.visual.base import (
    PAGE_TYPE_HOME,
    VARIANT_DESKTOP,
    VisualAuditReport,
    VisualPageReport,
    VisualSignal,
)
from src.visual.config import VisualConfig
from src.visual.score import label_for_score, score_site
from src.visual.signals import (
    SIGNAL_CLUTTER,
    SIGNAL_MODERN,
    SIGNAL_STRONG_BRAND,
    SIGNAL_WEAK_CTA,
    SIGNAL_WEAK_HIERARCHY,
    SIGNAL_WEAK_MOBILE,
)

# Site-level aggregation: counts, summary and the LLM banner. Pure functions
# over page reports; storage/dashboard/CSV all consume the same dicts.

CSV_FIELDS = [
    "visual_score",
    "visual_health_label",
    "visual_summary",
    "pages_with_weak_mobile_signal",
    "pages_with_clutter_signal",
    "pages_with_weak_cta_signal",
    "pages_with_strong_brand_signal",
    "pages_with_weak_hierarchy_signal",
]


@dataclass(frozen=True)
class PageEntry:
    url: str
    page_type: str
    variant: str
    screenshot_path: Optional[str]
    screenshot_hash: Optional[str]
    signals: tuple[VisualSignal, ...] = ()
    score: int = 100
    subscores: dict[str, int] = field(default_factory=dict)
    confidence: float = 0.0


def merge_page_entries(entries: list[PageEntry]) -> VisualPageReport:
    """Merge per-variant entries of one URL into a single page report.

    Desktop entries win for the primary screenshot; scores and sub-qualities
    are confidence-weighted across the variants captured.
    """
    desktop = [e for e in entries if e.variant == VARIANT_DESKTOP]
    mobile = [e for e in entries if e.variant != VARIANT_DESKTOP]
    primary = desktop or mobile

    signals = _dedupe_signals([signal for entry in entries for signal in entry.signals])
    score = int(round(_weighted_mean([e.score for e in entries], [e.confidence for e in entries])))
    subscores: dict[str, int] = {}
    for key in primary[0].subscores:
        subscores[key] = int(
            round(_weighted_mean([e.subscores.get(key, 100) for e in entries], [e.confidence for e in entries]))
        )

    issues = _sorted_details(signals, kind="issue")
    strengths = _sorted_details(signals, kind="strength")
    evidence: dict[str, Any] = {}
    for entry in entries:
        evidence[entry.variant] = {
            "score": entry.score,
            "confidence": round(entry.confidence, 3),
            "full_page": None,
        }

    return VisualPageReport(
        url=primary[0].url,
        page_type=primary[0].page_type,
        screenshot_available=bool(desktop),
        mobile_screenshot_available=bool(mobile),
        screenshot_path=desktop[0].screenshot_path if desktop else primary[0].screenshot_path,
        mobile_screenshot_path=mobile[0].screenshot_path if mobile else None,
        screenshot_hash=desktop[0].screenshot_hash if desktop else primary[0].screenshot_hash,
        visual_score=score,
        layout_quality=subscores.get("layout_quality", 100),
        readability_quality=subscores.get("readability_quality", 100),
        branding_quality=subscores.get("branding_quality", 100),
        mobile_quality=subscores.get("mobile_quality", 100),
        conversion_quality=subscores.get("conversion_quality", 100),
        confidence=round(sum(e.confidence for e in entries) / max(1, len(entries)), 3),
        issues=tuple(issues),
        strengths=tuple(strengths),
        evidence=evidence,
        signals=signals,
    )


def build_report(
    lead_url: str,
    page_reports: list[VisualPageReport],
    config: VisualConfig,
    llm_result: Optional[dict[str, Any]] = None,
) -> VisualAuditReport:
    """Aggregate page reports into the site-level audit report.

    ``llm_result`` (from the optional multimodal summarizer) is a dict with
    ``summary``, ``issues`` and ``strengths``; its observations are merged into
    the site-level lists so the dashboard shows them alongside the
    deterministic findings.
    """
    ordered = sorted(
        page_reports,
        key=lambda page: (0 if page.page_type == PAGE_TYPE_HOME else 1, page.url),
    )
    visual_score = score_site(ordered, config)
    label = label_for_score(visual_score, config)

    def _count(marker: str) -> int:
        return sum(1 for page in ordered if marker in page.signal_names())

    llm_summary_text: Optional[str] = None
    llm_issues: list[str] = []
    llm_strengths: list[str] = []
    if isinstance(llm_result, dict):
        llm_summary_text = llm_result.get("summary")
        llm_issues = list(llm_result.get("issues") or [])
        llm_strengths = list(llm_result.get("strengths") or [])

    issues = llm_issues + [issue for page in ordered for issue in page.issues]
    strengths = llm_strengths + [strength for page in ordered for strength in page.strengths]
    summary = llm_summary_text or _template_summary(visual_score, label, ordered, issues, strengths)

    return VisualAuditReport(
        lead_url=lead_url,
        visual_score=visual_score,
        visual_health_label=label,
        summary=summary,
        total_pages_audited=len(ordered),
        pages_with_desktop_screenshot=sum(1 for page in ordered if page.screenshot_available),
        pages_with_mobile_screenshot=sum(1 for page in ordered if page.mobile_screenshot_available),
        pages_with_modern_design_signal=_count(SIGNAL_MODERN),
        pages_with_clutter_signal=_count(SIGNAL_CLUTTER),
        pages_with_weak_hierarchy_signal=_count(SIGNAL_WEAK_HIERARCHY),
        pages_with_weak_mobile_signal=_count(SIGNAL_WEAK_MOBILE),
        pages_with_weak_cta_signal=_count(SIGNAL_WEAK_CTA),
        pages_with_strong_brand_signal=_count(SIGNAL_STRONG_BRAND),
        llm_summary=llm_summary_text,
        pages=tuple(ordered),
    )


def to_llm_text(report: VisualAuditReport) -> str:
    """Concise markdown banner consumed by the LLM as neutral context."""
    if report.total_pages_audited == 0:
        return "Site visual audit: not available (no screenshots captured).\n"

    screenshot_count = report.pages_with_desktop_screenshot + report.pages_with_mobile_screenshot
    lines = [
        "Site visual audit (deterministic local checks of screenshots; neutral context):",
        f"- Visual presentation: {report.visual_score}/100 ({report.visual_health_label}), "
        f"{report.total_pages_audited} page(s), {screenshot_count} screenshot(s)",
        f"- Pages with cluttered layout: {report.pages_with_clutter_signal}",
        f"- Pages with weak hierarchy: {report.pages_with_weak_hierarchy_signal}",
        f"- Pages with weak mobile layout: {report.pages_with_weak_mobile_signal}",
        f"- Pages with weak call-to-action: {report.pages_with_weak_cta_signal}",
        f"- Pages with modern design signal: {report.pages_with_modern_design_signal}",
        f"- Pages with strong branding: {report.pages_with_strong_brand_signal}",
    ]
    issues = [issue for page in report.pages for issue in page.issues][:5]
    strengths = [strength for page in report.pages for strength in page.strengths][:5]
    if issues:
        lines.append("- Top issues:")
        for issue in issues:
            lines.append(f"    - {issue}")
    else:
        lines.append("- No significant visual issues detected.")
    if strengths:
        lines.append("- Observed strengths:")
        for strength in strengths:
            lines.append(f"    - {strength}")
    return "\n".join(lines) + "\n"


def csv_fields(report: VisualAuditReport) -> dict[str, Any]:
    """Flat CSV-friendly summary for the pipeline export."""
    return {
        "visual_score": report.visual_score,
        "visual_health_label": report.visual_health_label,
        "visual_summary": report.summary,
        "pages_with_weak_mobile_signal": report.pages_with_weak_mobile_signal,
        "pages_with_clutter_signal": report.pages_with_clutter_signal,
        "pages_with_weak_cta_signal": report.pages_with_weak_cta_signal,
        "pages_with_strong_brand_signal": report.pages_with_strong_brand_signal,
        "pages_with_weak_hierarchy_signal": report.pages_with_weak_hierarchy_signal,
    }


def csv_fields_from_row(row: dict[str, Any]) -> dict[str, Any]:
    """CSV summary derived from a stored visual_audits row (export-time path)."""
    return {
        "visual_score": int(row.get("visual_score") or 0),
        "visual_health_label": str(row.get("visual_health_label") or ""),
        "visual_summary": str(row.get("summary") or ""),
        "pages_with_weak_mobile_signal": int(row.get("pages_with_weak_mobile_signal") or 0),
        "pages_with_clutter_signal": int(row.get("pages_with_clutter_signal") or 0),
        "pages_with_weak_cta_signal": int(row.get("pages_with_weak_cta_signal") or 0),
        "pages_with_strong_brand_signal": int(row.get("pages_with_strong_brand_signal") or 0),
        "pages_with_weak_hierarchy_signal": int(row.get("pages_with_weak_hierarchy_signal") or 0),
    }


def _template_summary(
    score: int,
    label: str,
    pages: list[VisualPageReport],
    issues: list[str],
    strengths: list[str],
) -> str:
    parts = [
        f"{label} visual presentation ({score}/100) based on {len(pages)} audited page(s)."
    ]
    if issues:
        parts.append("Top issues: " + "; ".join(issues[:3]))
    if strengths:
        parts.append("Strengths: " + "; ".join(strengths[:3]))
    return " ".join(parts)


def _sorted_details(signals: tuple[VisualSignal, ...], kind: str) -> list[str]:
    order = {"high": 0, "medium": 1, "low": 2}
    matches = sorted(
        (signal for signal in signals if signal.kind == kind),
        key=lambda signal: (order.get(signal.confidence, 3), signal.detail),
    )
    return list(dict.fromkeys(signal.detail for signal in matches))


def _dedupe_signals(signals: list[VisualSignal]) -> tuple[VisualSignal, ...]:
    order = {"high": 0, "medium": 1, "low": 2}
    seen: dict[str, VisualSignal] = {}
    for signal in signals:
        current = seen.get(signal.name)
        if current is None or order.get(signal.confidence, 3) < order.get(current.confidence, 3):
            seen[signal.name] = signal
    ranked = sorted(seen.values(), key=lambda signal: (order.get(signal.confidence, 3), signal.name))
    return tuple(ranked)


def _weighted_mean(values: list[int], weights: list[float]) -> float:
    if not values:
        return 100.0
    total_weight = sum(max(0.0, w) for w in weights)
    if total_weight <= 0.0:
        return sum(values) / len(values)
    return sum(value * max(0.0, weight) for value, weight in zip(values, weights)) / total_weight
