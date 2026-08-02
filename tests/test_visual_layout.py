import tempfile
import unittest
from pathlib import Path

from src.visual.config import VisualConfig
from src.visual.layout import LayoutMetrics, analyze_layout

from tests.visual_fixtures import (
    cluttered_image,
    low_contrast_image,
    modern_clean_image,
    solid_image,
    test_config,
)


class TestAnalyzeLayout(unittest.TestCase):
    def setUp(self) -> None:
        self._dir = tempfile.mkdtemp(prefix="layout_")
        self.cfg = test_config()

    def _path(self, name: str) -> str:
        return str(Path(self._dir) / name)

    def test_missing_file_returns_none(self) -> None:
        self.assertIsNone(analyze_layout(self._path("nope.png"), self.cfg))

    def test_corrupt_file_returns_none(self) -> None:
        path = self._path("bad.png")
        Path(path).write_bytes(b"not an image")
        self.assertIsNone(analyze_layout(path, self.cfg))

    def test_solid_white_metrics(self) -> None:
        path = self._path("w.png")
        solid_image((255, 255, 255))(path)
        m = analyze_layout(path, self.cfg)
        self.assertIsInstance(m, LayoutMetrics)
        assert m is not None
        self.assertEqual(round(m.ink_ratio, 2), 0.0)
        self.assertEqual(m.region_count, 0)

    def test_dense_image_has_high_ink(self) -> None:
        path = self._path("c.png")
        cluttered_image()(path)
        m = analyze_layout(path, self.cfg)
        assert m is not None
        self.assertGreater(m.ink_ratio, 0.2)
        self.assertGreaterEqual(m.region_count, 5)

    def test_low_contrast_image_has_low_contrast_std(self) -> None:
        path = self._path("g.png")
        low_contrast_image()(path)
        m = analyze_layout(path, self.cfg)
        assert m is not None
        self.assertLess(m.contrast_std, 40.0)

    def test_modern_image_has_diverse_palette(self) -> None:
        path = self._path("m.png")
        modern_clean_image()(path)
        m = analyze_layout(path, self.cfg)
        assert m is not None
        self.assertGreaterEqual(len(m.palette), 3)

    def test_to_dict_is_serializable(self) -> None:
        path = self._path("w.png")
        solid_image((0, 0, 0))(path)
        m = analyze_layout(path, self.cfg)
        assert m is not None
        d = m.to_dict()
        self.assertIn("ink_ratio", d)
        self.assertIsInstance(d["palette"], list)


if __name__ == "__main__":
    unittest.main()
