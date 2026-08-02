"""Synthetic fixtures for the visual audit tests (no network, no live sites).

Image generators are deterministic (no randomness) so pixel-derived metrics are
stable across runs. ``FakeScreenshoter`` implements the async ``screenshot``
contract the capture/engine layers expect, writing a real PNG to the requested
path and returning a ``ScreenshotResult`` with a caller-controlled probe dict.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any, Callable, Optional

from PIL import Image, ImageDraw

from src.scraping.browser_fetch import ScreenshotResult
from src.visual.config import VisualConfig

ImageWriter = Callable[[str], None]


def tmp_screenshot_dir() -> Path:
    return Path(tempfile.mkdtemp(prefix="visual_test_"))


def test_config(**overrides: Any) -> VisualConfig:
    """A small, fast VisualConfig rooted at a temp screenshot directory."""
    base: dict[str, Any] = {
        "enabled": True,
        "screenshot_dir": tmp_screenshot_dir(),
        "max_screenshots": 5,
        "max_internal_pages": 3,
    }
    base.update(overrides)
    return VisualConfig(**base)


# --- deterministic image generators -----------------------------------------


def solid_image(
    color: tuple[int, int, int], size: tuple[int, int] = (200, 150)
) -> ImageWriter:
    def write(path: str) -> None:
        Image.new("RGB", size, color).save(path)

    return write


def blocks_image(
    size: tuple[int, int],
    blocks: list[tuple[int, int, int, int, tuple[int, int, int]]],
    bg: tuple[int, int, int] = (255, 255, 255),
) -> ImageWriter:
    def write(path: str) -> None:
        img = Image.new("RGB", size, bg)
        draw = ImageDraw.Draw(img)
        for x0, y0, x1, y1, color in blocks:
            draw.rectangle([x0, y0, x1, y1], fill=color)
        img.save(path)

    return write


def cluttered_image(size: tuple[int, int] = (200, 150)) -> ImageWriter:
    """Six separate dark blocks in a 3x2 grid -> high ink + many regions."""
    w, h = size
    bw, bh = 45, 25
    positions = [
        (8, 8), (78, 8), (148, 8),
        (8, 70), (78, 70), (148, 70),
    ]
    blocks = [(x, y, x + bw, y + bh, (5, 5, 5)) for x, y in positions]
    return blocks_image(size, blocks)


def image_heavy_image(size: tuple[int, int] = (200, 150)) -> ImageWriter:
    """Very dense dark blocks -> ink ratio >= 0.50 and region count >= 10."""
    w, h = size
    bw, bh = w // 5, h // 5
    positions = [
        (x, y)
        for y in range(4, h - bh, bh + 3)
        for x in range(4, w - bw, bw + 3)
    ][:14]
    blocks = [(x, y, x + bw, y + bh, (10, 10, 10)) for x, y in positions]
    return blocks_image(size, blocks)


def modern_clean_image(size: tuple[int, int] = (200, 150)) -> ImageWriter:
    """A few distinct bright blocks on white -> balanced palette + contrast."""
    w, h = size
    blocks = [
        (10, 10, 70, 50, (30, 80, 200)),
        (w - 80, 10, w - 10, 50, (30, 160, 70)),
        (10, h - 60, 70, h - 10, (210, 120, 20)),
        (w - 80, h - 60, w - 10, h - 10, (180, 40, 60)),
    ]
    return blocks_image(size, blocks)


def low_contrast_image(size: tuple[int, int] = (200, 150)) -> ImageWriter:
    """Near-uniform mid-gray -> very low luminance spread."""
    return solid_image((128, 128, 128), size)


def uniform_dark_image(size: tuple[int, int] = (200, 150)) -> ImageWriter:
    """Solid dark fill -> high ink, zero variance, single region."""
    return solid_image((10, 10, 10), size)


def sparse_image(size: tuple[int, int] = (200, 150)) -> ImageWriter:
    """Mostly white with one tiny dark dot -> very low ink ratio."""
    w, h = size
    return blocks_image(size, [(w // 2 - 5, h // 2 - 5, w // 2 + 5, h // 2 + 5, (0, 0, 0))])


# --- probes -----------------------------------------------------------------

DESKTOP_PROBE: dict[str, Any] = {
    "horizontal_overflow": False,
    "cta_count": 3,
    "tel_links": 1,
    "mailto_links": 1,
    "scroll_height": 900,
    "inner_width": 1365,
    "inner_height": 900,
}

MOBILE_PROBE_OK: dict[str, Any] = {
    "horizontal_overflow": False,
    "cta_count": 1,
    "tel_links": 1,
    "mailto_links": 0,
    "scroll_height": 900,
    "inner_width": 390,
    "inner_height": 844,
}

MOBILE_PROBE_OVERFLOW: dict[str, Any] = {
    "horizontal_overflow": True,
    "cta_count": 0,
    "tel_links": 0,
    "mailto_links": 0,
    "scroll_height": 2400,
    "inner_width": 390,
    "inner_height": 844,
}


# --- fake fetcher -----------------------------------------------------------


class FakeScreenshoter:
    """Async stub implementing ``screenshot(url, path, width, height, ...)``.

    Picks an image writer by URL (falling back to desktop/mobile defaults based
    on the requested width) and returns a ``ScreenshotResult`` with the matching
    probe. ``failing_urls`` force an error result so tests can exercise the
    graceful-fallback path.
    """

    def __init__(
        self,
        *,
        desktop_image: ImageWriter,
        mobile_image: ImageWriter,
        desktop_probe: Optional[dict[str, Any]] = None,
        mobile_probe: Optional[dict[str, Any]] = None,
        url_images: Optional[dict[str, ImageWriter]] = None,
        url_probes: Optional[dict[str, dict[str, Any]]] = None,
        failing_urls: Optional[set[str]] = None,
    ) -> None:
        self._desktop_image = desktop_image
        self._mobile_image = mobile_image
        self._desktop_probe = desktop_probe or DESKTOP_PROBE
        self._mobile_probe = mobile_probe or MOBILE_PROBE_OK
        self._url_images = url_images or {}
        self._url_probes = url_probes or {}
        self._failing = failing_urls or set()
        self.captured: list[tuple[str, int, int]] = []

    async def screenshot(
        self,
        url: str,
        path: str,
        width: int = 1365,
        height: int = 900,
        max_full_height: int = 12000,
    ) -> ScreenshotResult:
        if url in self._failing:
            return ScreenshotResult(
                url=url, final_url=None, width=width, height=height,
                full_page=False, probe={}, error="boom",
            )
        is_mobile = width <= 500
        writer = self._url_images.get(url) or (
            self._mobile_image if is_mobile else self._desktop_image
        )
        probe = self._url_probes.get(url) or (
            self._mobile_probe if is_mobile else self._desktop_probe
        )
        writer(path)
        self.captured.append((url, width, height))
        return ScreenshotResult(
            url=url, final_url=url, width=width, height=height,
            full_page=True, probe=probe, error=None,
        )

    async def fetch(self, url: str) -> Any:
        raise NotImplementedError("FakeScreenshoter only supports screenshot()")


def crawl_pages(urls: list[str]) -> list[dict[str, Any]]:
    return [{"url": u, "label": "INTERNAL", "text": "page content"} for u in urls]



