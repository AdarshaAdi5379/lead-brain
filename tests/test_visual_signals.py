import unittest

from src.visual.base import VARIANT_DESKTOP, VARIANT_MOBILE
from src.visual.config import VisualConfig
from src.visual.layout import LayoutMetrics
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
    detect_branding_signals,
    detect_signals,
)

CONFIG = VisualConfig()


def _metrics(**kw) -> LayoutMetrics:
    defaults = dict(
        width=96, height=72, ink_ratio=0.2, whitespace_ratio=0.8,
        row_variance=0.1, region_count=3, hero_density=0.2,
        contrast_std=80.0,
        palette=((255, 255, 255), (30, 80, 200), (30, 160, 70), (210, 120, 20)),
        dominant_color=(255, 255, 255), dominant_share=0.4,
    )
    defaults.update(kw)
    return LayoutMetrics(**defaults)


def _names(signals) -> set[str]:
    return {s.name for s in signals}


class TestDetectSignals(unittest.TestCase):
    def test_clutter_fires_on_dense_many_regions(self) -> None:
        m = _metrics(ink_ratio=0.40, region_count=8)
        names = _names(detect_signals(m, {"cta_count": 3}, [], VARIANT_DESKTOP, CONFIG))
        self.assertIn(SIGNAL_CLUTTER, names)

    def test_weak_hierarchy_fires_on_uniform_density(self) -> None:
        m = _metrics(row_variance=0.01, ink_ratio=0.50, region_count=2)
        names = _names(detect_signals(m, {"cta_count": 3}, [], VARIANT_DESKTOP, CONFIG))
        self.assertIn(SIGNAL_WEAK_HIERARCHY, names)

    def test_weak_mobile_overflow(self) -> None:
        m = _metrics(ink_ratio=0.20, region_count=3)
        names = _names(detect_signals(m, {"horizontal_overflow": True}, [], VARIANT_MOBILE, CONFIG))
        self.assertIn(SIGNAL_WEAK_MOBILE, names)

    def test_weak_mobile_cramped(self) -> None:
        m = _metrics(ink_ratio=0.40, region_count=6)
        names = _names(detect_signals(m, {"horizontal_overflow": False}, [], VARIANT_MOBILE, CONFIG))
        self.assertIn(SIGNAL_WEAK_MOBILE, names)

    def test_weak_cta_when_none(self) -> None:
        names = _names(detect_signals(_metrics(), {"cta_count": 0}, [], VARIANT_DESKTOP, CONFIG))
        self.assertIn(SIGNAL_WEAK_CTA, names)

    def test_weak_cta_when_single(self) -> None:
        names = _names(detect_signals(_metrics(), {"cta_count": 1}, [], VARIANT_DESKTOP, CONFIG))
        self.assertIn(SIGNAL_WEAK_CTA, names)

    def test_strong_cta_when_multiple(self) -> None:
        names = _names(detect_signals(_metrics(), {"cta_count": 3}, [], VARIANT_DESKTOP, CONFIG))
        self.assertIn(SIGNAL_STRONG_CTA, names)
        self.assertNotIn(SIGNAL_WEAK_CTA, names)

    def test_low_contrast(self) -> None:
        m = _metrics(contrast_std=20.0)
        names = _names(detect_signals(m, {"cta_count": 3}, [], VARIANT_DESKTOP, CONFIG))
        self.assertIn(SIGNAL_LOW_CONTRAST, names)

    def test_outdated_limited_palette_low_contrast(self) -> None:
        m = _metrics(contrast_std=20.0, palette=((255, 255, 255), (10, 10, 10)))
        names = _names(detect_signals(m, {"cta_count": 3}, [], VARIANT_DESKTOP, CONFIG))
        self.assertIn(SIGNAL_OUTDATED, names)

    def test_image_heavy_implies_clutter(self) -> None:
        m = _metrics(ink_ratio=0.60, region_count=12)
        names = _names(detect_signals(m, {"cta_count": 3}, [], VARIANT_DESKTOP, CONFIG))
        self.assertIn(SIGNAL_IMAGE_HEAVY, names)
        self.assertIn(SIGNAL_CLUTTER, names)

    def test_modern_balanced_palette(self) -> None:
        names = _names(detect_signals(_metrics(), {"cta_count": 3}, [], VARIANT_DESKTOP, CONFIG))
        self.assertIn(SIGNAL_MODERN, names)

    def test_strong_brand_dominant_color(self) -> None:
        names = _names(detect_signals(_metrics(), {"cta_count": 3}, [], VARIANT_DESKTOP, CONFIG))
        self.assertIn(SIGNAL_STRONG_BRAND, names)

    def test_responsive_when_mobile_fits(self) -> None:
        m = _metrics(ink_ratio=0.20, region_count=3)
        names = _names(detect_signals(m, {"horizontal_overflow": False}, [], VARIANT_MOBILE, CONFIG))
        self.assertIn(SIGNAL_RESPONSIVE, names)
        self.assertNotIn(SIGNAL_WEAK_MOBILE, names)

    def test_modern_tech_evidence_raises_confidence(self) -> None:
        detections = [{"technology_name": "React", "category": "frontend"}]
        signals = detect_signals(_metrics(), {"cta_count": 3}, detections, VARIANT_DESKTOP, CONFIG)
        modern = next(s for s in signals if s.name == SIGNAL_MODERN)
        self.assertEqual(modern.confidence, "high")

    def test_sparse_fires_on_low_ink_desktop(self) -> None:
        m = _metrics(ink_ratio=0.03)
        names = _names(detect_signals(m, {"cta_count": 3}, [], VARIANT_DESKTOP, CONFIG))
        self.assertIn(SIGNAL_SPARSE, names)

    def test_text_heavy_with_page_context(self) -> None:
        m = _metrics(ink_ratio=0.3, region_count=3)
        ctx = {"word_count": 800, "image_count": 1}
        names = _names(detect_signals(m, {"cta_count": 3}, [], VARIANT_DESKTOP, CONFIG, page_context=ctx))
        self.assertIn(SIGNAL_TEXT_HEAVY, names)

    def test_text_heavy_not_fired_without_context(self) -> None:
        names = _names(detect_signals(_metrics(), {"cta_count": 3}, [], VARIANT_DESKTOP, CONFIG))
        self.assertNotIn(SIGNAL_TEXT_HEAVY, names)

    def test_mobile_no_cta_fires_on_empty_mobile(self) -> None:
        m = _metrics(ink_ratio=0.2, region_count=2)
        names = _names(detect_signals(m, {"horizontal_overflow": False, "cta_count": 0},
                                      [], VARIANT_MOBILE, CONFIG))
        self.assertIn(SIGNAL_MOBILE_NO_CTA, names)

    def test_contact_visible_fires_when_tel_present(self) -> None:
        names = _names(detect_signals(_metrics(), {"cta_count": 0, "tel_links": 1, "mailto_links": 0},
                                      [], VARIANT_DESKTOP, CONFIG))
        self.assertIn(SIGNAL_CONTACT_VISIBLE, names)

    def test_long_scroll_fires_when_page_very_tall(self) -> None:
        probe = {"cta_count": 3, "scroll_height": 2800, "inner_height": 900}
        names = _names(detect_signals(_metrics(), probe, [], VARIANT_DESKTOP, CONFIG))
        self.assertIn(SIGNAL_LONG_SCROLL, names)

    def test_long_scroll_not_fired_when_short(self) -> None:
        probe = {"cta_count": 3, "scroll_height": 900, "inner_height": 900}
        names = _names(detect_signals(_metrics(), probe, [], VARIANT_DESKTOP, CONFIG))
        self.assertNotIn(SIGNAL_LONG_SCROLL, names)


class TestBrandingSignals(unittest.TestCase):
    def _palette(self, colors):  # type: ignore[no-untyped-def]
        return tuple(colors)

    def test_consistent_palettes(self) -> None:
        pal = [(100, 100, 100), (200, 200, 200)]
        signals = detect_branding_signals(
            [("u1", self._palette(pal)), ("u2", self._palette([(105, 105, 105), (195, 195, 195)]))],
            CONFIG,
        )
        self.assertIn(SIGNAL_BRANDING_CONSISTENT, _names(signals))

    def test_inconsistent_palettes(self) -> None:
        signals = detect_branding_signals(
            [("u1", self._palette([(255, 0, 0), (0, 255, 0), (0, 0, 255)])),
             ("u2", self._palette([(255, 255, 255), (255, 255, 255), (255, 255, 255)]))],
            CONFIG,
        )
        self.assertIn(SIGNAL_BRANDING_INCONSISTENT, _names(signals))

    def test_too_few_palettes_returns_empty(self) -> None:
        self.assertEqual(detect_branding_signals([("u", self._palette([(0, 0, 0)]))], CONFIG), [])


if __name__ == "__main__":
    unittest.main()
