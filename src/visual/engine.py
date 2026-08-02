from __future__ import annotations

from dataclasses import replace
from typing import Any, Optional, Sequence

from src.visual.base import VisualAuditReport, VisualPageReport, VisualSignal
from src.visual.capture import _capture_for_lead_async
from src.visual.config import VisualConfig
from src.visual.layout import analyze_layout
from src.visual.report import PageEntry, build_report, merge_page_entries
from src.visual.score import score_page
from src.visual.signals import detect_branding_signals, detect_signals

# Orchestration: capture -> layout analysis -> signals -> scoring -> report.
# Pure deterministic steps in sequence; the optional vision summarizer is
# env-gated and never required for a report.


async def run_visual_audit(
    fetcher: Any,
    home_url: str,
    crawl_pages: Any,
    detections: Sequence[dict[str, Any]],
    config: VisualConfig,
    *,
    page_context: Optional[dict[str, dict[str, Any]]] = None,
) -> Optional[VisualAuditReport]:
    """Run the full visual audit for one lead; None when nothing was captured.

    ``page_context`` optionally maps a page URL to text-derived signals
    (word_count, image_count, title) from the crawl/SEO layers, enriching the
    pixel-only heuristics without any extra network access.
    """
    if not config.enabled:
        return None

    refs = await _capture_for_lead_async(fetcher, home_url, crawl_pages, config)
    if not refs:
        return None

    entries: list[PageEntry] = []
    desktop_palettes: list[tuple[str, tuple[tuple[int, int, int], ...]]] = []
    for ref in refs:
        metrics = analyze_layout(ref.path, config)
        if metrics is None:
            continue
        ctx = page_context.get(ref.url) if page_context else None
        signals = detect_signals(metrics, ref.probe, detections, ref.variant, config, page_context=ctx)
        score, subscores = score_page(signals, config)
        confidence = _page_confidence(signals)
        entries.append(
            PageEntry(
                url=ref.url,
                page_type=ref.page_type,
                variant=ref.variant,
                screenshot_path=ref.path,
                screenshot_hash=ref.screenshot_hash,
                signals=tuple(signals),
                score=score,
                subscores=subscores,
                confidence=confidence,
            )
        )
        if ref.variant == "desktop":
            desktop_palettes.append((ref.url, metrics.palette))

    if not entries:
        return None

    grouped: dict[str, list[PageEntry]] = {}
    for entry in entries:
        grouped.setdefault(entry.url, []).append(entry)
    page_reports = [merge_page_entries(group) for group in grouped.values()]

    branding_signals = detect_branding_signals(desktop_palettes, config)
    if branding_signals:
        page_reports = [
            _apply_site_signals(page, branding_signals, config) for page in page_reports
        ]

    llm_result = None
    if config.llm_enabled:
        from src.visual.summarizer import summarize_visual

        llm_result = summarize_visual(refs, config)

    return build_report(home_url, page_reports, config, llm_result=llm_result)


def _page_confidence(signals: list[VisualSignal]) -> float:
    """Mean confidence factor of the detected signals (0 when none fired)."""
    if not signals:
        return 0.0
    return sum(signal.weight for signal in signals) / len(signals)


def _apply_site_signals(
    page: VisualPageReport,
    extra: Sequence[VisualSignal],
    config: VisualConfig,
) -> VisualPageReport:
    """Fold site-level (cross-page) signals into a page report + re-score."""
    from src.visual.report import _sorted_details

    signals = list(page.signals) + list(extra)
    score, subscores = score_page(signals, config)
    issues = tuple(_sorted_details(tuple(signals), kind="issue"))
    strengths = tuple(_sorted_details(tuple(signals), kind="strength"))
    return replace(
        page,
        signals=tuple(signals),
        visual_score=score,
        layout_quality=subscores["layout_quality"],
        readability_quality=subscores["readability_quality"],
        branding_quality=subscores["branding_quality"],
        mobile_quality=subscores["mobile_quality"],
        conversion_quality=subscores["conversion_quality"],
        issues=issues,
        strengths=strengths,
    )
