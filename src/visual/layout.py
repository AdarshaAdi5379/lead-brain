from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from src.visual.config import VisualConfig
from src.visual.heuristics import (
    contrast_std,
    dominant_color_share,
    ink_ratio,
    open_grid,
    open_rgb_grid,
    palette,
    region_count,
    row_variance,
    top_density,
    whitespace_ratio,
)

# Spatial layout analysis: one pass over the downscaled grid producing a
# compact LayoutMetrics object consumed by the signal detector. Pure + safe;
# a missing or corrupt image yields None, never an exception.


@dataclass(frozen=True)
class LayoutMetrics:
    width: int
    height: int
    ink_ratio: float
    whitespace_ratio: float
    row_variance: float
    region_count: int
    hero_density: float
    contrast_std: float
    palette: tuple[tuple[int, int, int], ...]
    dominant_color: Optional[tuple[int, int, int]]
    dominant_share: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "width": self.width,
            "height": self.height,
            "ink_ratio": round(self.ink_ratio, 4),
            "whitespace_ratio": round(self.whitespace_ratio, 4),
            "row_variance": round(self.row_variance, 4),
            "region_count": self.region_count,
            "hero_density": round(self.hero_density, 4),
            "contrast_std": round(self.contrast_std, 2),
            "palette": [list(color) for color in self.palette],
            "dominant_color": list(self.dominant_color) if self.dominant_color else None,
            "dominant_share": round(self.dominant_share, 4),
        }


def analyze_layout(path: str, config: VisualConfig) -> Optional[LayoutMetrics]:
    """Analyze one screenshot file; None when the image is unreadable."""
    gray = open_grid(path, config.analysis_grid)
    rgb = open_rgb_grid(path, config.analysis_grid)
    if gray is None or rgb is None:
        return None

    dominant, share = dominant_color_share(rgb, config.palette_size)
    return LayoutMetrics(
        width=gray.width,
        height=gray.height,
        ink_ratio=ink_ratio(gray),
        whitespace_ratio=whitespace_ratio(gray),
        row_variance=row_variance(gray),
        region_count=region_count(gray),
        hero_density=top_density(gray, band=config.hero_band),
        contrast_std=contrast_std(gray),
        palette=tuple(palette(rgb, config.palette_size, samples=config.palette_size)),
        dominant_color=dominant,
        dominant_share=share,
    )
