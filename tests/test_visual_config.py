import unittest
from types import SimpleNamespace

from src.visual.config import VisualConfig, confidence_weight, from_settings, health_for_score


class TestHealthForScore(unittest.TestCase):
    def test_bands(self) -> None:
        cfg = VisualConfig()
        self.assertEqual(health_for_score(90, cfg), "Excellent")
        self.assertEqual(health_for_score(85, cfg), "Excellent")
        self.assertEqual(health_for_score(75, cfg), "Good")
        self.assertEqual(health_for_score(70, cfg), "Good")
        self.assertEqual(health_for_score(60, cfg), "Fair")
        self.assertEqual(health_for_score(50, cfg), "Fair")
        self.assertEqual(health_for_score(40, cfg), "Poor")
        self.assertEqual(health_for_score(30, cfg), "Poor")
        self.assertEqual(health_for_score(20, cfg), "Critical")
        self.assertEqual(health_for_score(0, cfg), "Critical")


class TestConfidenceWeight(unittest.TestCase):
    def test_factors(self) -> None:
        cfg = VisualConfig()
        self.assertEqual(confidence_weight("high", cfg), cfg.confidence_high)
        self.assertEqual(confidence_weight("medium", cfg), cfg.confidence_medium)
        self.assertEqual(confidence_weight("low", cfg), cfg.confidence_low)
        self.assertEqual(confidence_weight("unknown", cfg), cfg.confidence_low)


class TestFromSettings(unittest.TestCase):
    def test_defaults_when_settings_empty(self) -> None:
        cfg = from_settings(SimpleNamespace())
        self.assertTrue(cfg.enabled)
        self.assertFalse(cfg.recapture)
        self.assertFalse(cfg.llm_enabled)

    def test_reads_bool_flags(self) -> None:
        settings = SimpleNamespace(
            VISUAL_ENABLED=False,
            VISUAL_RECAPTURE=True,
            VISUAL_LLM_ENABLED=True,
            VISUAL_LLM_MODEL="gpt-4o",
        )
        cfg = from_settings(settings)
        self.assertFalse(cfg.enabled)
        self.assertTrue(cfg.recapture)
        self.assertTrue(cfg.llm_enabled)
        self.assertEqual(cfg.llm_model, "gpt-4o")

    def test_parses_viewport_string(self) -> None:
        settings = SimpleNamespace(VISUAL_VIEWPORT_DESKTOP="1024x768")
        cfg = from_settings(settings)
        self.assertEqual(cfg.viewport_desktop, (1024, 768))

    def test_bad_viewport_falls_back(self) -> None:
        settings = SimpleNamespace(VISUAL_VIEWPORT_MOBILE="nonsense")
        cfg = from_settings(settings)
        self.assertEqual(cfg.viewport_mobile, VisualConfig().viewport_mobile)


if __name__ == "__main__":
    unittest.main()
