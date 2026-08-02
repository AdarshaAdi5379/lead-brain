from __future__ import annotations

from dataclasses import dataclass

from src.fingerprinting.base import (
    Detection,
    FingerprintCatalog,
    Signal,
    Technology,
    load_catalog,
)
from src.fingerprinting.cookies import CookieEvidence, build_cookie_evidence
from src.fingerprinting.headers import HeaderEvidence, build_evidence as build_header_evidence
from src.fingerprinting.html import PageEvidence, build_page_evidence


@dataclass(frozen=True)
class SiteEvidence:
    """The consolidated deterministic evidence for one fetched response."""

    page: PageEvidence
    headers: HeaderEvidence
    cookies: CookieEvidence

    def match_signal(self, signal: Signal) -> str | None:
        """Run a single signal against the available evidence."""
        if signal.kind == "generator":
            return self.page.match_generator(signal.pattern)
        if signal.kind == "meta":
            return self.page.match_meta(signal.target, signal.pattern)
        if signal.kind == "html":
            return self.page.match_html(signal.pattern)
        if signal.kind == "script":
            return self.page.match_script(signal.pattern)
        if signal.kind == "style":
            return self.page.match_style(signal.pattern)
        if signal.kind == "global":
            return self.page.match_global(signal.pattern)
        if signal.kind == "header":
            return self.headers.match(signal.target, signal.pattern)
        if signal.kind == "cookie":
            return self.cookies.match(signal.pattern)
        if signal.kind == "canonical":
            return self.page.match_canonical(signal.pattern)
        if signal.kind == "path":
            # Endpoint probes are handled by the caller (see TechnologyDetector).
            return None
        if signal.kind == "class":
            return self.page.match_class(signal.pattern)
        if signal.kind == "id":
            return self.page.match_id(signal.pattern)
        return None


def build_site_evidence(
    html: str | None,
    headers: dict[str, str] | None = None,
    cookies: list[dict] | None = None,
) -> SiteEvidence:
    return SiteEvidence(
        page=build_page_evidence(html),
        headers=build_header_evidence(headers),
        cookies=build_cookie_evidence(cookies),
    )


@dataclass
class FingerprintResult:
    """Result of running the detector over one site response."""

    detections: tuple[Detection, ...]
    site_url: str | None

    def confidence(self, name: str) -> int:
        for detection in self.detections:
            if detection.name == name:
                return detection.confidence
        return 0

    def has(self, name: str) -> bool:
        return any(d.name == name for d in self.detections)

    def by_category(self, category: str) -> list[Detection]:
        return [d for d in self.detections if d.category == category]


class TechnologyDetector:
    """Deterministic fingerprint engine.

    Runs every technology's signals over evidence gathered from the already
    downloaded homepage response (HTML + HTTP headers + cookies). Endpoint
    probes (``path`` signals) are only consulted when ``allow_probes=True``
    and probe results are passed in; they never happen implicitly.
    """

    def __init__(
        self,
        catalog: FingerprintCatalog | None = None,
        min_confidence: int = 25,
    ) -> None:
        self.catalog = catalog or load_catalog()
        self.min_confidence = max(0, int(min_confidence))

    def detect(
        self,
        evidence: SiteEvidence,
        *,
        site_url: str | None = None,
        probe_results: dict[str, bool] | None = None,
    ) -> FingerprintResult:
        """Run all technologies against evidence; return sorted detections."""
        detections: list[Detection] = []
        for technology in self.catalog.all():
            confidence, evidence_strings = self._match(technology, evidence, probe_results)
            if confidence >= self.min_confidence:
                detections.append(
                    Detection(
                        name=technology.name,
                        category=technology.category,
                        confidence=confidence,
                        evidence=tuple(evidence_strings),
                    )
                )
        detections.sort(key=lambda d: (d.confidence, d.name), reverse=True)
        return FingerprintResult(detections=tuple(detections), site_url=site_url)

    def probe_paths(self, catalog: FingerprintCatalog | None = None) -> list[str]:
        """Well-known paths for optional endpoint probing (deduped)."""
        paths: list[str] = []
        seen: set[str] = set()
        for technology in (catalog or self.catalog).all():
            for signal in technology.signals:
                if signal.kind == "path" and signal.path and signal.path not in seen:
                    seen.add(signal.path)
                    paths.append(signal.path)
        return paths

    @staticmethod
    def _match(
        technology: Technology,
        evidence: SiteEvidence,
        probe_results: dict[str, bool] | None,
    ) -> tuple[int, list[str]]:
        confidence = 0
        matched: list[str] = []
        for signal in technology.signals:
            if signal.kind == "path":
                if probe_results and signal.path in probe_results:
                    if probe_results.get(signal.path):
                        confidence += signal.weight
                        matched.append(f"{signal.label()}: reachable")
                continue
            snippet = evidence.match_signal(signal)
            if snippet:
                confidence += signal.weight
                matched.append(f"{signal.label()}: {_short(snippet)}")
        return min(100, confidence), matched


def _short(text: str, limit: int = 80) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= limit else text[: limit - 1] + "…"