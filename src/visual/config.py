from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# Deterministic visual audit tunables. All thresholds live here so engine
# code never carries magic numbers (mirrors ScoringConfig / OpportunityConfig).

DESKTOP_VIEWPORT = (1365, 900)
MOBILE_VIEWPORT = (390, 844)


@dataclass(frozen=True)
class VisualConfig:
    enabled: bool = True
    recapture: bool = False
    screenshot_dir: Path = Path("data/screenshots")
    viewport_desktop: tuple[int, int] = DESKTOP_VIEWPORT
    viewport_mobile: tuple[int, int] = MOBILE_VIEWPORT
    max_screenshots: int = 5
    max_internal_pages: int = 3
    fullpage_max_height: int = 12_000
    analysis_grid: int = 96
    llm_enabled: bool = False
    llm_model: str = "gpt-4o-mini"
    llm_max_images: int = 2

    # Health bands (score -> label), inclusive minimums.
    excellent_min: int = 85
    good_min: int = 70
    fair_min: int = 50
    poor_min: int = 30

    # Confidence factors scale every signal's point contribution.
    confidence_high: float = 1.0
    confidence_medium: float = 0.6
    confidence_low: float = 0.3

    # Point tunables (applied as score = 100 + sum(weighted points)).
    modern_design_bonus: float = 5.0
    strong_brand_bonus: float = 5.0
    strong_cta_bonus: float = 3.0
    responsive_bonus: float = 3.0
    branding_consistent_bonus: float = 3.0
    outdated_design_penalty: float = 8.0
    clutter_penalty: float = 12.0
    weak_hierarchy_penalty: float = 10.0
    weak_mobile_penalty: float = 12.0
    weak_cta_penalty: float = 8.0
    low_contrast_penalty: float = 8.0
    branding_inconsistent_penalty: float = 6.0
    image_heavy_penalty: float = 4.0

    # Heuristic thresholds.
    ink_ratio_high: float = 0.30
    clutter_min_regions: int = 5
    hierarchy_min_row_var: float = 0.02
    hierarchy_min_ink: float = 0.08
    mobile_cramped_ink: float = 0.35
    image_heavy_ink: float = 0.50
    image_heavy_regions: int = 10
    contrast_min_std: float = 40.0
    hero_band: float = 0.45
    palette_size: int = 16
    outdated_max_colors: int = 2
    brand_diversity_min: int = 3
    brand_diversity_max: int = 8
    brand_dominant_min_share: float = 0.25
    brand_consistency_max_distance: float = 0.55
    brand_consistency_good_distance: float = 0.35
    palette_distance_samples: int = 8

    # Cross-page branding distance: pages compared pairwise, needs at least
    # this many page palettes before a consistency signal can fire.
    min_palettes_for_consistency: int = 2

    # --- additional layout / conversion signals ---
    # Sparse: ink ratio below this on a desktop page -> too little content.
    sparse_max_ink: float = 0.05
    sparse_penalty: float = 4.0
    # Text-heavy: high word count with very few images -> wall-of-text.
    text_heavy_min_words: int = 600
    text_heavy_max_images: int = 2
    text_heavy_penalty: float = 6.0
    # Mobile CTA invisible: no CTA elements detected on the mobile viewport.
    mobile_no_cta_penalty: float = 5.0
    # Contact action visible: tel:/mailto: links present (strength).
    contact_visible_bonus: float = 3.0
    # Long scroll: page height exceeds this many viewport heights.
    long_scroll_factor: float = 3.0
    long_scroll_penalty: float = 4.0


def from_settings(settings: object, defaults: Optional[VisualConfig] = None) -> VisualConfig:
    """Build a VisualConfig from the module-level settings object.

    Uses the defaults for anything the settings module does not define, so
    tests and non-pipeline callers can construct a config with plain values.
    """
    base = defaults or VisualConfig()

    def _bool(name: str, fallback: bool) -> bool:
        value = getattr(settings, name, None)
        if isinstance(value, bool):
            return value
        if value is None:
            return fallback
        return str(value).strip().lower() in {"1", "true", "yes", "on"}

    def _int(name: str, fallback: int) -> int:
        value = getattr(settings, name, fallback)
        return int(value) if value is not None else fallback

    def _float(name: str, fallback: float) -> float:
        value = getattr(settings, name, fallback)
        return float(value) if value is not None else fallback

    def _viewport(name: str, fallback: tuple[int, int]) -> tuple[int, int]:
        value = getattr(settings, name, None)
        if not value:
            return fallback
        try:
            parts = str(value).split("x")
            return (int(parts[0]), int(parts[1]))
        except (ValueError, IndexError):
            return fallback

    screenshot_dir = getattr(settings, "VISUAL_SCREENSHOT_DIR", None) or base.screenshot_dir

    return VisualConfig(
        enabled=_bool("VISUAL_ENABLED", base.enabled),
        recapture=_bool("VISUAL_RECAPTURE", base.recapture),
        screenshot_dir=Path(screenshot_dir),
        viewport_desktop=_viewport("VISUAL_VIEWPORT_DESKTOP", base.viewport_desktop),
        viewport_mobile=_viewport("VISUAL_VIEWPORT_MOBILE", base.viewport_mobile),
        fullpage_max_height=_int("VISUAL_FULLPAGE_MAX_HEIGHT", base.fullpage_max_height),
        llm_enabled=_bool("VISUAL_LLM_ENABLED", base.llm_enabled),
        llm_model=getattr(settings, "VISUAL_LLM_MODEL", None) or base.llm_model,
    )


def health_for_score(score: int, config: VisualConfig) -> str:
    """Map a 0-100 visual score to a health label."""
    if score >= config.excellent_min:
        return "Excellent"
    if score >= config.good_min:
        return "Good"
    if score >= config.fair_min:
        return "Fair"
    if score >= config.poor_min:
        return "Poor"
    return "Critical"


def confidence_weight(confidence: str, config: VisualConfig) -> float:
    if confidence == "high":
        return config.confidence_high
    if confidence == "medium":
        return config.confidence_medium
    return config.confidence_low
