from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

# Data contract for the local visual audit. Mirrors the SEO audit structure:
# pure dataclasses with to_dict(), so storage, dashboard and CSV export never
# depend on PIL or Playwright.

PAGE_TYPE_HOME = "home"
PAGE_TYPE_INTERNAL = "internal"
VARIANT_DESKTOP = "desktop"
VARIANT_MOBILE = "mobile"


@dataclass(frozen=True)
class VisualSignal:
    name: str
    detail: str
    kind: str  # "strength" | "issue"
    confidence: str  # "high" | "medium" | "low"
    weight: float
    points: float
    evidence: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "detail": self.detail,
            "kind": self.kind,
            "confidence": self.confidence,
            "weight": self.weight,
            "points": self.points,
            "evidence": list(self.evidence),
        }


@dataclass(frozen=True)
class VisualPageReport:
    url: str
    page_type: str
    screenshot_available: bool
    mobile_screenshot_available: bool
    screenshot_path: Optional[str] = None
    mobile_screenshot_path: Optional[str] = None
    screenshot_hash: Optional[str] = None
    visual_score: int = 100
    layout_quality: int = 100
    readability_quality: int = 100
    branding_quality: int = 100
    mobile_quality: int = 100
    conversion_quality: int = 100
    confidence: float = 0.0
    issues: tuple[str, ...] = ()
    strengths: tuple[str, ...] = ()
    evidence: dict[str, Any] = field(default_factory=dict)
    signals: tuple[VisualSignal, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "page_type": self.page_type,
            "screenshot_available": int(self.screenshot_available),
            "mobile_screenshot_available": int(self.mobile_screenshot_available),
            "screenshot_path": self.screenshot_path,
            "mobile_screenshot_path": self.mobile_screenshot_path,
            "screenshot_hash": self.screenshot_hash,
            "visual_score": self.visual_score,
            "layout_quality": self.layout_quality,
            "readability_quality": self.readability_quality,
            "branding_quality": self.branding_quality,
            "mobile_quality": self.mobile_quality,
            "conversion_quality": self.conversion_quality,
            "confidence": round(self.confidence, 3),
            "issues_json": _list_to_json(self.issues),
            "strengths_json": _list_to_json(self.strengths),
            "evidence_json": _json_dumps(self.evidence),
        }

    def signal_names(self) -> set[str]:
        return {signal.name for signal in self.signals}


@dataclass(frozen=True)
class VisualAuditReport:
    lead_url: str
    visual_score: int
    visual_health_label: str
    summary: str
    total_pages_audited: int
    pages_with_desktop_screenshot: int
    pages_with_mobile_screenshot: int
    pages_with_modern_design_signal: int
    pages_with_clutter_signal: int
    pages_with_weak_hierarchy_signal: int
    pages_with_weak_mobile_signal: int
    pages_with_weak_cta_signal: int
    pages_with_strong_brand_signal: int
    llm_summary: Optional[str] = None
    pages: tuple[VisualPageReport, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        data = {
            "lead_url": self.lead_url,
            "visual_score": self.visual_score,
            "visual_health_label": self.visual_health_label,
            "summary": self.summary,
            "total_pages_audited": self.total_pages_audited,
            "pages_with_desktop_screenshot": self.pages_with_desktop_screenshot,
            "pages_with_mobile_screenshot": self.pages_with_mobile_screenshot,
            "pages_with_modern_design_signal": self.pages_with_modern_design_signal,
            "pages_with_clutter_signal": self.pages_with_clutter_signal,
            "pages_with_weak_hierarchy_signal": self.pages_with_weak_hierarchy_signal,
            "pages_with_weak_mobile_signal": self.pages_with_weak_mobile_signal,
            "pages_with_weak_cta_signal": self.pages_with_weak_cta_signal,
            "pages_with_strong_brand_signal": self.pages_with_strong_brand_signal,
            "llm_summary": self.llm_summary,
            "pages": [page.to_dict() for page in self.pages],
        }
        return data


def _list_to_json(items: tuple[str, ...]) -> str:
    return _json_dumps(list(items))


def _json_dumps(value: Any) -> str:
    import json

    return json.dumps(value, ensure_ascii=False, default=str)
