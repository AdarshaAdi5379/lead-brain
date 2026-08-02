import unittest

from src.visual.base import VisualPageReport, VisualSignal
from src.visual.config import VisualConfig, health_for_score
from src.visual.report import PageEntry
from src.visual.score import label_for_score, score_page, score_site
from src.visual.signals import (
    SIGNAL_CLUTTER,
    SIGNAL_MODERN,
    SIGNAL_STRONG_BRAND,
    SIGNAL_WEAK_CTA,
)


def _signal(name: str, kind: str, points: float, confidence: str = "medium") -> VisualSignal:
    cfg = VisualConfig()
    signed = abs(points) if kind == "strength" else -abs(points)
    return VisualSignal(
        name=name, detail=name, kind=kind, confidence=confidence,
        weight={"high": 1.0, "medium": 0.6, "low": 0.3}[confidence],
        points=signed, evidence=(),
    )


class TestScorePage(unittest.TestCase):
    def test_no_signals_is_perfect(self) -> None:
        score, subs = score_page([], VisualConfig())
        self.assertEqual(score, 100)
        for key in subs:
            self.assertEqual(subs[key], 100)

    def test_penalty_lowers_score(self) -> None:
        score, _ = score_page([_signal(SIGNAL_CLUTTER, "issue", 12.0, "high")], VisualConfig())
        self.assertLess(score, 100)

    def test_bonus_raises_but_clamps_at_100(self) -> None:
        score, _ = score_page(
            [_signal(SIGNAL_MODERN, "strength", 50.0, "high")], VisualConfig()
        )
        self.assertEqual(score, 100)

    def test_score_clamps_to_zero(self) -> None:
        score, _ = score_page(
            [_signal(SIGNAL_CLUTTER, "issue", 200.0, "high")], VisualConfig()
        )
        self.assertEqual(score, 0)

    def test_subqualities_isolate_signals(self) -> None:
        subs = score_page([_signal(SIGNAL_WEAK_CTA, "issue", 8.0, "high")], VisualConfig())[1]
        self.assertLess(subs["conversion_quality"], 100)
        self.assertEqual(subs["layout_quality"], 100)


class TestScoreSite(unittest.TestCase):
    def test_empty_is_perfect(self) -> None:
        self.assertEqual(score_site([], VisualConfig()), 100)

    def test_single_page_returns_its_score(self) -> None:
        page = VisualPageReport(url="u", page_type="home", screenshot_available=True,
                                mobile_screenshot_available=False, visual_score=70)
        self.assertEqual(score_site([page], VisualConfig()), 70)

    def test_confidence_weighted_mean(self) -> None:
        a = VisualPageReport(url="a", page_type="home", screenshot_available=True,
                             mobile_screenshot_available=False, visual_score=80, confidence=2.0)
        b = VisualPageReport(url="b", page_type="internal", screenshot_available=True,
                             mobile_screenshot_available=False, visual_score=60, confidence=1.0)
        score = score_site([a, b], VisualConfig())
        self.assertEqual(score, 73)  # (80*2 + 60*1) / 3


class TestLabelForScore(unittest.TestCase):
    def test_delegates_to_health_for_score(self) -> None:
        cfg = VisualConfig()
        for value in (90, 75, 60, 40, 20):
            self.assertEqual(label_for_score(value, cfg), health_for_score(value, cfg))


if __name__ == "__main__":
    unittest.main()
