from __future__ import annotations

from typing import Optional

from PIL import Image

# Pixel-level computer-vision-lite primitives. Everything operates on a tiny
# downscaled grid (<= analysis_grid px) so worst-case memory is bounded
# regardless of the screenshot dimensions. Pure functions: no IO beyond
# reading the image the caller asks for, no network.

_GRID_TOLERANCE = 12
_MAX_DECODED_PIXELS = 30_000_000


def _pixel_values(image: Image.Image):
    """Iterate pixel values, compatible across Pillow versions.

    Pillow 12 deprecates ``getdata`` in favour of ``get_flattened_data``
    (removal planned for Pillow 14). Prefer the new API when present and fall
    back to ``getdata`` on older versions so ``requirements.txt``'s
    ``Pillow>=10`` keeps working.
    """
    getter = getattr(image, "get_flattened_data", None)
    if getter is not None:
        return getter()
    return image.getdata()


def open_grid(path: str, max_edge: int) -> Optional[Image.Image]:
    """Open an image and downscale it to a grayscale grid <= max_edge."""
    rgb = open_rgb_grid(path, max_edge)
    if rgb is None:
        return None
    return rgb.convert("L")


def open_rgb_grid(path: str, max_edge: int) -> Optional[Image.Image]:
    """Open an image and downscale it to an RGB grid <= max_edge.

    Returns None for missing, unreadable or oversized (decompression-bomb)
    images so callers can degrade gracefully.
    """
    try:
        with Image.open(path) as image:
            if (image.width or 0) * (image.height or 0) > _MAX_DECODED_PIXELS:
                return None
            if image.width <= 0 or image.height <= 0:
                return None
            image.load()
            scale = min(1.0, max_edge / max(image.width, image.height))
            width = max(1, int(image.width * scale))
            height = max(1, int(image.height * scale))
            return image.convert("RGB").resize((width, height))
    except (OSError, ValueError, SyntaxError):
        return None


def ink_mask(gray: Image.Image) -> Image.Image:
    """Binary mask: dark (ink) pixels are white (255), background is black (0)."""
    return gray.point(lambda pixel: 255 if pixel < _GRID_TOLERANCE else 0)


def ink_ratio(gray: Image.Image) -> float:
    """Fraction of non-background (ink) pixels in the grid."""
    total = gray.width * gray.height
    if total == 0:
        return 0.0
    dark = sum(1 for pixel in _pixel_values(ink_mask(gray)) if pixel)
    return dark / total


def whitespace_ratio(gray: Image.Image) -> float:
    return 1.0 - ink_ratio(gray)


def row_variance(gray: Image.Image) -> float:
    """Std-dev of per-row ink counts normalized by the pixel range (0..1)."""
    mask = ink_mask(gray)
    data = list(_pixel_values(mask))
    rows = [sum(data[row * gray.width : (row + 1) * gray.width]) for row in range(gray.height)]
    return _std(rows) / 255.0


def col_variance(gray: Image.Image) -> float:
    mask = ink_mask(gray)
    data = list(_pixel_values(mask))
    cols = [sum(data[col::gray.width]) for col in range(gray.width)]
    return _std(cols) / 255.0


def region_count(gray: Image.Image) -> int:
    """Number of connected ink regions (4-connectivity, iterative flood fill)."""
    mask = ink_mask(gray)
    width, height = mask.size
    data = list(_pixel_values(mask))
    if not data:
        return 0
    visited = [False] * len(data)
    count = 0
    stack: list[int] = []
    for start in range(len(data)):
        if not data[start] or visited[start]:
            continue
        count += 1
        visited[start] = True
        stack.append(start)
        while stack:
            index = stack.pop()
            x = index % width
            y = index // width
            for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                if 0 <= nx < width and 0 <= ny < height:
                    neighbor = ny * width + nx
                    if data[neighbor] and not visited[neighbor]:
                        visited[neighbor] = True
                        stack.append(neighbor)
    return count


def top_density(gray: Image.Image, band: float = 0.45) -> float:
    """Ink ratio inside the top ``band`` fraction of the grid (hero area)."""
    height = max(1, int(gray.height * band))
    top = gray.crop((0, 0, gray.width, height))
    return ink_ratio(top)


def contrast_std(gray: Image.Image) -> float:
    """Std-dev of luminance over the grid (proxy for color contrast)."""
    return _std(list(_pixel_values(gray)))


def palette(rgb: Image.Image, colors: int, samples: int = 16) -> list[tuple[int, int, int]]:
    """Dominant colors via median-cut quantization, most frequent first."""
    quantized, palette_colors = _quantize(rgb, colors)
    counts: dict[tuple[int, int, int], int] = {}
    for index in _pixel_values(quantized):
        color = _palette_rgb(palette_colors, index)
        counts[color] = counts.get(color, 0) + 1
    ranked = sorted(counts.items(), key=lambda item: item[1], reverse=True)
    return [tuple(color) for color, _ in ranked[:samples]]


def dominant_color_share(
    rgb: Image.Image, colors: int
) -> tuple[Optional[tuple[int, int, int]], float]:
    """Most frequent color and its share of all grid pixels."""
    ranked = palette(rgb, colors, samples=1)
    if not ranked:
        return (None, 0.0)
    dominant = ranked[0]
    total = rgb.width * rgb.height
    if total == 0:
        return (dominant, 0.0)
    quantized, palette_colors = _quantize(rgb, colors)
    share = sum(1 for index in _pixel_values(quantized) if _palette_rgb(palette_colors, index) == dominant)
    return (dominant, share / total)


def _quantize(rgb: Image.Image, colors: int) -> tuple[Image.Image, list[int]]:
    quantized = rgb.quantize(colors=max(2, colors), method=Image.MEDIANCUT)
    return quantized, (quantized.getpalette() or [])


def _palette_rgb(palette_colors: list[int], index: int) -> tuple[int, int, int]:
    offset = index * 3
    return (
        palette_colors[offset],
        palette_colors[offset + 1],
        palette_colors[offset + 2],
    )


def palette_distance(pal_a: list[tuple[int, int, int]], pal_b: list[tuple[int, int, int]]) -> float:
    """Mean of per-color nearest-neighbor distances, normalized to ~0..1.

    Greedy nearest-neighbor matching; deterministic for the same inputs.
    """
    if not pal_a or not pal_b:
        return 0.0
    total = 0.0
    for color_a in pal_a:
        best = min(_color_distance(color_a, color_b) for color_b in pal_b)
        total += best
    return (total / len(pal_a)) / 441.0


def _color_distance(a: tuple[int, int, int], b: tuple[int, int, int]) -> float:
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2) ** 0.5


def _std(values: list[int]) -> float:
    if not values:
        return 0.0
    mean = sum(values) / len(values)
    variance = sum((value - mean) ** 2 for value in values) / len(values)
    return variance ** 0.5
