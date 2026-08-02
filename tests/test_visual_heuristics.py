import os
import tempfile
import unittest
from pathlib import Path

from src.visual import heuristics
from src.visual.heuristics import (
    contrast_std,
    dominant_color_share,
    ink_ratio,
    open_grid,
    open_rgb_grid,
    palette,
    palette_distance,
    region_count,
    row_variance,
    whitespace_ratio,
)

from tests.visual_fixtures import (
    cluttered_image,
    image_heavy_image,
    low_contrast_image,
    modern_clean_image,
    solid_image,
)


class TestImageLoading(unittest.TestCase):
    def setUp(self) -> None:
        self._dir = tempfile.mkdtemp(prefix="heur_")

    def _path(self, name: str) -> str:
        return str(Path(self._dir) / name)

    def test_open_grid_missing_file_returns_none(self) -> None:
        self.assertIsNone(open_grid(self._path("nope.png"), 96))

    def test_open_grid_corrupt_file_returns_none(self) -> None:
        path = self._path("bad.png")
        Path(path).write_bytes(b"not a png at all")
        self.assertIsNone(open_grid(path, 96))
        self.assertIsNone(open_rgb_grid(path, 96))

    def test_open_grid_valid_returns_grayscale(self) -> None:
        path = self._path("ok.png")
        solid_image((0, 0, 0))(path)
        gray = open_grid(path, 96)
        self.assertIsNotNone(gray)
        self.assertEqual(gray.mode, "L")

    def test_open_grid_oversized_is_rejected(self) -> None:
        path = self._path("big.png")
        solid_image((0, 0, 0), (200, 150))(path)
        original = heuristics._MAX_DECODED_PIXELS
        heuristics._MAX_DECODED_PIXELS = 1
        try:
            self.assertIsNone(open_rgb_grid(path, 96))
        finally:
            heuristics._MAX_DECODED_PIXELS = original


class TestPixelPrimitives(unittest.TestCase):
    def setUp(self) -> None:
        self._dir = tempfile.mkdtemp(prefix="heur2_")

    def _path(self, name: str) -> str:
        return str(Path(self._dir) / name)

    def test_ink_ratio_extremes(self) -> None:
        white = self._path("w.png")
        black = self._path("b.png")
        solid_image((255, 255, 255))(white)
        solid_image((0, 0, 0))(black)
        self.assertEqual(ink_ratio(open_grid(white, 96)), 0.0)
        self.assertEqual(round(ink_ratio(open_grid(black, 96)), 2), 1.0)

    def test_whitespace_ratio_inverse(self) -> None:
        white = self._path("w.png")
        solid_image((255, 255, 255))(white)
        self.assertEqual(whitespace_ratio(open_grid(white, 96)), 1.0)

    def test_row_variance_solid_is_zero(self) -> None:
        black = self._path("b.png")
        solid_image((0, 0, 0))(black)
        self.assertEqual(row_variance(open_grid(black, 96)), 0.0)

    def test_region_count_extremes(self) -> None:
        white = self._path("w.png")
        black = self._path("b.png")
        solid_image((255, 255, 255))(white)
        solid_image((0, 0, 0))(black)
        self.assertEqual(region_count(open_grid(white, 96)), 0)
        self.assertEqual(region_count(open_grid(black, 96)), 1)

    def test_contrast_std_solid_is_zero(self) -> None:
        gray = self._path("g.png")
        solid_image((128, 128, 128))(gray)
        self.assertEqual(contrast_std(open_grid(gray, 96)), 0.0)

    def test_palette_returns_dominant_colors(self) -> None:
        path = self._path("m.png")
        modern_clean_image()(path)
        colors = palette(open_rgb_grid(path, 96), 8)
        self.assertTrue(len(colors) > 1)
        self.assertTrue(all(len(c) == 3 for c in colors))

    def test_dominant_color_share_solid(self) -> None:
        path = self._path("s.png")
        solid_image((10, 20, 30))(path)
        color, share = dominant_color_share(open_rgb_grid(path, 96), 8)
        self.assertIsNotNone(color)
        self.assertGreater(share, 0.95)

    def test_palette_distance_identical_is_zero(self) -> None:
        pal = [(255, 0, 0), (0, 255, 0)]
        self.assertEqual(palette_distance(pal, pal), 0.0)

    def test_palette_distance_divergent_is_high(self) -> None:
        a = [(255, 0, 0), (0, 255, 0), (0, 0, 255)]
        b = [(255, 255, 255), (255, 255, 255), (255, 255, 255)]
        self.assertGreater(palette_distance(a, b), 0.5)


if __name__ == "__main__":
    unittest.main()
