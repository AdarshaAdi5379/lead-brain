from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class Severity(str, Enum):
    CRITICAL = "critical"
    MAJOR = "major"
    MODERATE = "moderate"
    MINOR = "minor"
    INFO = "info"


SEVERITY_PENALTY: dict[Severity, int] = {
    Severity.CRITICAL: 25,
    Severity.MAJOR: 15,
    Severity.MODERATE: 10,
    Severity.MINOR: 5,
    Severity.INFO: 0,
}

# Score bands for the overall health label (site and page level).
HEALTH_BANDS: list[tuple[int, str]] = [
    (90, "Excellent"),
    (75, "Good"),
    (60, "Fair"),
    (40, "Poor"),
]


def health_for_score(score: int) -> str:
    for threshold, label in HEALTH_BANDS:
        if score >= threshold:
            return label
    return "Critical"


@dataclass(frozen=True)
class SeoIssue:
    severity: Severity
    code: str
    reason: str
    fix: str

    def to_dict(self) -> dict[str, str]:
        return {
            "severity": self.severity.value,
            "code": self.code,
            "reason": self.reason,
            "fix": self.fix,
        }


@dataclass(frozen=True)
class PageEvidence:
    """Every raw SEO signal the deterministic parser can extract from a page."""

    url: str
    is_https: bool
    title: str
    meta_description: str
    canonical_url: Optional[str]
    robots_meta: str
    viewport_present: bool
    h1_count: int
    h2_count: int
    h3_count: int
    word_count: int
    image_count: int
    images_missing_alt_count: int
    images_broken_count: int
    json_ld_present: bool
    schema_present: bool
    og_title_present: bool
    og_description_present: bool
    twitter_card_present: bool
    favicon_present: bool
    internal_link_count: int
    mixed_content_count: int
    sitemap_reference: bool
    robots_txt_reference: bool
    page_type: Optional[str]


@dataclass(frozen=True)
class PageSeoAudit:
    url: str
    page_type: Optional[str]
    html_available: bool
    title_present: bool
    title_length: int
    meta_description_present: bool
    meta_description_length: int
    h1_count: int
    h2_count: int
    canonical_present: bool
    robots_meta: bool
    viewport_present: bool
    noindex: bool
    nofollow: bool
    word_count: int
    image_count: int
    images_missing_alt_count: int
    json_ld_present: bool
    schema_present: bool
    og_title_present: bool
    og_description_present: bool
    twitter_card_present: bool
    internal_link_count: int
    issues: tuple[SeoIssue, ...] = field(default_factory=tuple)
    score: int = 100
    health: str = "Excellent"
    title: str = ""
    meta_description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "page_type": self.page_type,
            "html_available": int(self.html_available),
            "title_present": int(self.title_present),
            "title_length": self.title_length,
            "meta_description_present": int(self.meta_description_present),
            "meta_description_length": self.meta_description_length,
            "h1_count": self.h1_count,
            "h2_count": self.h2_count,
            "canonical_present": int(self.canonical_present),
            "robots_meta": int(self.robots_meta),
            "viewport_present": int(self.viewport_present),
            "noindex": int(self.noindex),
            "nofollow": int(self.nofollow),
            "word_count": self.word_count,
            "image_count": self.image_count,
            "images_missing_alt_count": self.images_missing_alt_count,
            "json_ld_present": int(self.json_ld_present),
            "schema_present": int(self.schema_present),
            "og_title_present": int(self.og_title_present),
            "og_description_present": int(self.og_description_present),
            "twitter_card_present": int(self.twitter_card_present),
            "internal_link_count": self.internal_link_count,
            "issues_json": _issues_to_json(self.issues),
            "score": self.score,
            "health": self.health,
        }


@dataclass(frozen=True)
class SiteSeoAudit:
    lead_url: str
    site_score: int
    overall_health: str
    total_pages_audited: int
    html_pages: int
    pages_with_title: int
    pages_with_meta_description: int
    pages_with_h1: int
    pages_with_multiple_h1: int
    pages_with_noindex: int
    pages_with_canonical: int
    pages_with_json_ld: int
    pages_with_images_missing_alt: int
    pages_with_duplicate_titles: int
    pages_with_duplicate_descriptions: int
    pages_with_thin_content: int
    robots_txt_detected: bool
    sitemap_detected: bool
    severity_summary: tuple[SeoIssue, ...] = field(default_factory=tuple)
    pages: tuple[PageSeoAudit, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "lead_url": self.lead_url,
            "site_score": self.site_score,
            "overall_health": self.overall_health,
            "total_pages_audited": self.total_pages_audited,
            "html_pages": self.html_pages,
            "pages_with_title": self.pages_with_title,
            "pages_with_meta_description": self.pages_with_meta_description,
            "pages_with_h1": self.pages_with_h1,
            "pages_with_multiple_h1": self.pages_with_multiple_h1,
            "pages_with_noindex": self.pages_with_noindex,
            "pages_with_canonical": self.pages_with_canonical,
            "pages_with_json_ld": self.pages_with_json_ld,
            "pages_with_images_missing_alt": self.pages_with_images_missing_alt,
            "pages_with_duplicate_titles": self.pages_with_duplicate_titles,
            "pages_with_duplicate_descriptions": self.pages_with_duplicate_descriptions,
            "pages_with_thin_content": self.pages_with_thin_content,
            "robots_txt_detected": int(self.robots_txt_detected),
            "sitemap_detected": int(self.sitemap_detected),
            "severity_summary": [issue.to_dict() for issue in self.severity_summary],
            "pages": [page.to_dict() for page in self.pages],
        }


def _issues_to_json(issues: tuple[SeoIssue, ...]) -> str:
    import json

    return json.dumps([issue.to_dict() for issue in issues], ensure_ascii=False)
