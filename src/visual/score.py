from __future__ import annotations

from src.visual.base import VisualPageReport, VisualSignal
from src.visual.config import VisualConfig, health_for_score
from src.visual.signals import (
    SIGNAL_BRANDING_CONSISTENT,
    SIGNAL_BRANDING_INCONSISTENT,
    SIGNAL_CLUTTER,
    SIGNAL_CONTACT_VISIBLE,
    SIGNAL_IMAGE_HEAVY,
    SIGNAL_LONG_SCROLL,
    SIGNAL_LOW_CONTRAST,
    SIGNAL_MOBILE_NO_CTA,
    SIGNAL_MODERN,
    SIGNAL_OUTDATED,
    SIGNAL_RESPONSIVE,
    SIGNAL_SPARSE,
    SIGNAL_STRONG_BRAND,
    SIGNAL_STRONG_CTA,
    SIGNAL_TEXT_HEAVY,
    SIGNAL_WEAK_CTA,
    SIGNAL_WEAK_HIERARCHY,
    SIGNAL_WEAK_MOBILE,
)

# Deterministic page/site scoring. Start at 100, apply confidence-weighted
# signal points, clamp to 0-100. Sub-qualities group the same signals so the
# dashboard can show where a page loses points.

SUBQUALITY_SIGNALS: dict[str, set[str]] = {
    "layout_quality": {
        SIGNAL_CLUTTER, SIGNAL_WEAK_HIERARCHY, SIGNAL_IMAGE_HEAVY,
        SIGNAL_MODERN, SIGNAL_OUTDATED, SIGNAL_SPARSE, SIGNAL_LONG_SCROLL,
    },
    "readability_quality": {
        SIGNAL_LOW_CONTRAST, SIGNAL_IMAGE_HEAVY, SIGNAL_MODERN, SIGNAL_TEXT_HEAVY,
    },
    "branding_quality": {
        SIGNAL_MODERN,
        SIGNAL_OUTDATED,
        SIGNAL_STRONG_BRAND,
        SIGNAL_BRANDING_INCONSISTENT,
        SIGNAL_BRANDING_CONSISTENT,
    },
    "mobile_quality": {SIGNAL_WEAK_MOBILE, SIGNAL_RESPONSIVE, SIGNAL_MOBILE_NO_CTA},
    "conversion_quality": {
        SIGNAL_WEAK_CTA, SIGNAL_STRONG_CTA,
        SIGNAL_MOBILE_NO_CTA, SIGNAL_CONTACT_VISIBLE,
    },
}


def label_for_score(score: int, config: VisualConfig) -> str:
    return health_for_score(int(score), config)


def _clamp(value: float) -> int:
    return int(round(max(0.0, min(100.0, value))))


def weighted_points(signals: list[VisualSignal]) -> float:
    return sum(signal.weight * signal.points for signal in signals)


def score_page(signals: list[VisualSignal], config: VisualConfig) -> tuple[int, dict[str, int]]:
    """Page visual score + per-sub-quality breakdown (0-100 each)."""
    subscores: dict[str, int] = {}
    for quality, members in SUBQUALITY_SIGNALS.items():
        member_points = sum(
            signal.weight * signal.points
            for signal in signals
            if signal.name in members
        )
        subscores[quality] = _clamp(100 + member_points)
    return _clamp(100 + weighted_points(signals)), subscores


def score_site(pages: list[VisualPageReport], config: VisualConfig) -> int:
    """Confidence-weighted mean of page scores (fallback: plain mean)."""
    if not pages:
        return 100
    total_confidence = sum(max(0.0, page.confidence) for page in pages)
    if total_confidence <= 0.0:
        return _clamp(sum(page.visual_score for page in pages) / len(pages))
    weighted = sum(page.visual_score * max(0.0, page.confidence) for page in pages)
    return _clamp(weighted / total_confidence)
