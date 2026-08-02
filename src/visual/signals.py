from __future__ import annotations

from typing import Any, Optional, Sequence

from src.visual.base import VARIANT_MOBILE, VisualSignal
from src.visual.config import VisualConfig, confidence_weight
from src.visual.layout import LayoutMetrics

# Deterministic signal detection over layout metrics + the browser probe.
# Confidence is intentionally conservative: pixels alone rarely justify a
# "high" claim, and fingerprint data is only supporting evidence.

SIGNAL_MODERN = "modern_design"
SIGNAL_OUTDATED = "outdated_design"
SIGNAL_CLUTTER = "clutter"
SIGNAL_WEAK_HIERARCHY = "weak_hierarchy"
SIGNAL_WEAK_MOBILE = "weak_mobile"
SIGNAL_WEAK_CTA = "weak_cta"
SIGNAL_STRONG_BRAND = "strong_brand"
SIGNAL_STRONG_CTA = "strong_cta"
SIGNAL_RESPONSIVE = "responsive"
SIGNAL_LOW_CONTRAST = "low_contrast"
SIGNAL_IMAGE_HEAVY = "image_heavy"
SIGNAL_BRANDING_INCONSISTENT = "branding_inconsistent"
SIGNAL_BRANDING_CONSISTENT = "branding_consistent"
SIGNAL_SPARSE = "sparse_layout"
SIGNAL_TEXT_HEAVY = "text_heavy"
SIGNAL_MOBILE_NO_CTA = "mobile_no_cta"
SIGNAL_CONTACT_VISIBLE = "contact_visible"
SIGNAL_LONG_SCROLL = "long_scroll"

_MODERN_FRAMEWORKS = (
    "react",
    "vue",
    "next.js",
    "nuxt",
    "svelte",
    "astro",
    "gatsby",
    "angular",
    "remix",
    "tailwind",
)


def detect_signals(
    metrics: LayoutMetrics,
    probe: dict[str, Any],
    detections: Sequence[dict[str, Any]],
    variant: str,
    config: VisualConfig,
    *,
    page_context: Optional[dict[str, Any]] = None,
) -> list[VisualSignal]:
    """Detect strengths/issues for one screenshot (pure, deterministic).

    ``page_context`` optionally carries text-derived signals (word count, image
    count) from the crawl/SEO layers so pixel-only heuristics can be enriched
    without re-fetching anything.
    """
    signals: list[VisualSignal] = []
    modern_evidence = _modern_tech_evidence(detections)
    palette_size = len(metrics.palette)

    # --- Issues ---
    if metrics.ink_ratio >= config.ink_ratio_high and metrics.region_count >= config.clutter_min_regions:
        confidence = "high" if metrics.ink_ratio >= config.image_heavy_ink else "medium"
        signals.append(
            _signal(
                SIGNAL_CLUTTER,
                f"Cluttered layout: dense content ({metrics.ink_ratio:.0%} ink) split into "
                f"{metrics.region_count} blocks",
                "issue",
                confidence,
                config.clutter_penalty,
                (f"ink_ratio={metrics.ink_ratio:.2f}", f"region_count={metrics.region_count}"),
                config,
            )
        )

    if (
        metrics.row_variance < config.hierarchy_min_row_var
        and metrics.ink_ratio >= config.hierarchy_min_ink
        and metrics.region_count < config.clutter_min_regions
    ):
        signals.append(
            _signal(
                SIGNAL_WEAK_HIERARCHY,
                "Weak visual hierarchy: uniform content density, no clear sections",
                "issue",
                "medium",
                config.weak_hierarchy_penalty,
                (f"row_variance={metrics.row_variance:.3f}",),
                config,
            )
        )

    if variant == VARIANT_MOBILE:
        overflow = bool(probe.get("horizontal_overflow"))
        if overflow:
            signals.append(
                _signal(
                    SIGNAL_WEAK_MOBILE,
                    "Horizontal overflow on the mobile viewport; layout is not responsive",
                    "issue",
                    "high",
                    config.weak_mobile_penalty,
                    ("horizontal_overflow=true",),
                    config,
                )
            )
        elif metrics.ink_ratio >= config.mobile_cramped_ink and metrics.region_count >= config.clutter_min_regions:
            signals.append(
                _signal(
                    SIGNAL_WEAK_MOBILE,
                    "Cramped mobile layout: content fills the viewport edge to edge",
                    "issue",
                    "medium",
                    config.weak_mobile_penalty,
                    (f"ink_ratio={metrics.ink_ratio:.2f}", f"region_count={metrics.region_count}"),
                    config,
                )
            )

    cta_count = probe.get("cta_count")
    if variant != VARIANT_MOBILE and isinstance(cta_count, int):
        if cta_count <= 0:
            signals.append(
                _signal(
                    SIGNAL_WEAK_CTA,
                    "No clear call-to-action button detected in the viewport",
                    "issue",
                    "high",
                    config.weak_cta_penalty,
                    ("cta_count=0",),
                    config,
                )
            )
        elif cta_count == 1:
            signals.append(
                _signal(
                    SIGNAL_WEAK_CTA,
                    "Only a single weak call-to-action detected in the viewport",
                    "issue",
                    "low",
                    config.weak_cta_penalty,
                    ("cta_count=1",),
                    config,
                )
            )

    if metrics.contrast_std < config.contrast_min_std:
        signals.append(
            _signal(
                SIGNAL_LOW_CONTRAST,
                "Low color contrast; text and elements may be hard to read",
                "issue",
                "medium",
                config.low_contrast_penalty,
                (f"contrast_std={metrics.contrast_std:.1f}",),
                config,
            )
        )

    if palette_size <= config.outdated_max_colors and metrics.contrast_std < config.contrast_min_std:
        if not modern_evidence:
            signals.append(
                _signal(
                    SIGNAL_OUTDATED,
                    "Outdated look: very limited palette and low contrast",
                    "issue",
                    "medium",
                    config.outdated_design_penalty,
                    (f"palette_size={palette_size}",),
                    config,
                )
            )

    if metrics.ink_ratio >= config.image_heavy_ink and metrics.region_count >= config.image_heavy_regions:
        signals.append(
            _signal(
                SIGNAL_IMAGE_HEAVY,
                "Image-heavy page may load slowly and bury content",
                "issue",
                "low",
                config.image_heavy_penalty,
                (f"ink_ratio={metrics.ink_ratio:.2f}", f"region_count={metrics.region_count}"),
                config,
            )
        )

    if variant != VARIANT_MOBILE and metrics.ink_ratio < config.sparse_max_ink:
        signals.append(
            _signal(
                SIGNAL_SPARSE,
                "Page appears sparse: very little visible content",
                "issue",
                "low",
                config.sparse_penalty,
                (f"ink_ratio={metrics.ink_ratio:.2f}",),
                config,
            )
        )

    if page_context:
        word_count = page_context.get("word_count")
        image_count = page_context.get("image_count")
        if isinstance(word_count, (int, float)) and isinstance(image_count, (int, float)):
            if word_count >= config.text_heavy_min_words and image_count <= config.text_heavy_max_images:
                signals.append(
                    _signal(
                        SIGNAL_TEXT_HEAVY,
                        "Text-heavy page with few images (wall-of-text appearance)",
                        "issue",
                        "medium",
                        config.text_heavy_penalty,
                        (f"word_count={int(word_count)}", f"image_count={int(image_count)}"),
                        config,
                    )
                )

    if variant == VARIANT_MOBILE and isinstance(cta_count, int) and cta_count <= 0:
        signals.append(
            _signal(
                SIGNAL_MOBILE_NO_CTA,
                "No call-to-action visible on the mobile viewport",
                "issue",
                "medium",
                config.mobile_no_cta_penalty,
                ("cta_count=0",),
                config,
            )
        )

    scroll_height = probe.get("scroll_height")
    inner_height = probe.get("inner_height")
    if (
        isinstance(scroll_height, (int, float))
        and isinstance(inner_height, (int, float))
        and inner_height > 0
        and scroll_height > config.long_scroll_factor * inner_height
    ):
        signals.append(
            _signal(
                SIGNAL_LONG_SCROLL,
                "Page requires excessive vertical scrolling",
                "issue",
                "low",
                config.long_scroll_penalty,
                (f"scroll_height={int(scroll_height)}", f"inner_height={int(inner_height)}"),
                config,
            )
        )

    # --- Strengths ---
    if config.brand_diversity_min <= palette_size <= config.brand_diversity_max:
        if metrics.contrast_std >= config.contrast_min_std:
            confidence = "high" if modern_evidence else "medium"
            signals.append(
                _signal(
                    SIGNAL_MODERN,
                    "Modern design: balanced palette with clear contrast",
                    "strength",
                    confidence,
                    config.modern_design_bonus,
                    (f"palette_size={palette_size}", f"contrast_std={metrics.contrast_std:.1f}"),
                    config,
                )
            )

    if metrics.dominant_share >= config.brand_dominant_min_share and palette_size >= 2:
        signals.append(
            _signal(
                SIGNAL_STRONG_BRAND,
                f"Consistent brand color dominates ({metrics.dominant_share:.0%} of pixels)",
                "strength",
                "medium",
                config.strong_brand_bonus,
                (f"dominant_share={metrics.dominant_share:.2f}",),
                config,
            )
        )

    if variant != VARIANT_MOBILE and isinstance(cta_count, int) and cta_count >= 2:
        signals.append(
            _signal(
                SIGNAL_STRONG_CTA,
                f"{cta_count} clear call-to-action elements in the viewport",
                "strength",
                "medium",
                config.strong_cta_bonus,
                (f"cta_count={cta_count}",),
                config,
            )
        )

    tel_links = probe.get("tel_links")
    mailto_links = probe.get("mailto_links")
    if (isinstance(tel_links, int) and tel_links > 0) or (
        isinstance(mailto_links, int) and mailto_links > 0
    ):
        signals.append(
            _signal(
                SIGNAL_CONTACT_VISIBLE,
                "Contact action (phone/email link) visible on the page",
                "strength",
                "medium",
                config.contact_visible_bonus,
                (f"tel_links={tel_links or 0}", f"mailto_links={mailto_links or 0}"),
                config,
            )
        )

    if variant == VARIANT_MOBILE and not bool(probe.get("horizontal_overflow")):
        if metrics.ink_ratio <= config.mobile_cramped_ink:
            signals.append(
                _signal(
                    SIGNAL_RESPONSIVE,
                    "Layout fits the mobile viewport without overflow",
                    "strength",
                    "medium",
                    config.responsive_bonus,
                    ("horizontal_overflow=false",),
                    config,
                )
            )

    return signals


def detect_branding_signals(
    page_palettes: Sequence[tuple[str, tuple[tuple[int, int, int], ...]]],
    config: VisualConfig,
) -> list[VisualSignal]:
    """Cross-page branding consistency from desktop palettes (pure)."""
    palettes = [palette for _, palette in page_palettes if palette]
    if len(palettes) < config.min_palettes_for_consistency:
        return []

    worst = 0.0
    for i in range(len(palettes)):
        for j in range(i + 1, len(palettes)):
            distance = _palette_distance_avg(palettes[i], palettes[j], config)
            worst = max(worst, distance)

    if worst >= config.brand_consistency_max_distance:
        return [
            _signal(
                SIGNAL_BRANDING_INCONSISTENT,
                "Branding differs noticeably across pages (colors/palette not consistent)",
                "issue",
                "medium",
                config.branding_inconsistent_penalty,
                (f"max_palette_distance={worst:.2f}",),
                config,
            )
        ]
    if worst <= config.brand_consistency_good_distance:
        return [
            _signal(
                SIGNAL_BRANDING_CONSISTENT,
                "Consistent branding and color palette across pages",
                "strength",
                "medium",
                config.branding_consistent_bonus,
                (f"max_palette_distance={worst:.2f}",),
                config,
            )
        ]
    return []


def _palette_distance_avg(
    a: tuple[tuple[int, int, int], ...],
    b: tuple[tuple[int, int, int], ...],
    config: VisualConfig,
) -> float:
    from src.visual.heuristics import palette_distance

    return palette_distance(list(a), list(b))


def _modern_tech_evidence(detections: Sequence[dict[str, Any]]) -> tuple[str, ...]:
    """Modern frontend frameworks found by the fingerprint engine (if any)."""
    evidence: list[str] = []
    for detection in detections:
        name = str(detection.get("technology_name") or "").lower()
        if any(framework in name for framework in _MODERN_FRAMEWORKS):
            evidence.append(name)
    return tuple(evidence)


def _signal(
    name: str,
    detail: str,
    kind: str,
    confidence: str,
    points: float,
    evidence: tuple[str, ...],
    config: VisualConfig,
) -> VisualSignal:
    signed_points = abs(points) if kind == "strength" else -abs(points)
    return VisualSignal(
        name=name,
        detail=detail,
        kind=kind,
        confidence=confidence,
        weight=confidence_weight(confidence, config),
        points=signed_points,
        evidence=evidence,
    )
