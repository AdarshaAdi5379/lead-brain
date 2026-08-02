from __future__ import annotations

from typing import Any, Optional

from src.opportunities.base import Opportunity, severity_for_score
from src.opportunities.config import OpportunityConfig
from src.scoring.base import LeadScore, ScoringInputs
from src.scoring.rules import (
    as_int,
    clamp,
    detection_categories,
    detection_names,
    has_text,
    has_contact_page,
    has_services_page,
    has_about_page,
    is_https_url,
    safe_lower,
    safe_str,
)

# Technology names/categories the detectors key off (single source of truth).
ANALYTICS_NAMES = {
    "google analytics",
    "google tag manager",
    "facebook pixel",
    "hotjar",
    "microsoft clarity",
}
ECOMMERCE_PLATFORMS = {"shopify", "magento", "woocommerce", "bigcommerce"}
ECOMMERCE_NAMES = {"woocommerce", "shopify storefront", "stripe", "razorpay", "paypal"}
RESPONSIVE_FRAMEWORKS = {"bootstrap", "tailwind css"}
LEGACY_LIBRARIES = {"jquery", "alpine.js"}


def build_opportunity(
    category: str,
    points: int,
    evidence: list[str],
    config: OpportunityConfig,
) -> Optional[Opportunity]:
    """Assemble a deterministic Opportunity from raw detector signals.

    Applies the configured score bands and confidence model, and drops
    opportunities below the minimum detectable score.
    """
    score = clamp(points)
    if score < config.min_detectable_score:
        return None
    severity = severity_for_score(score, config.severity_bands)
    confidence = clamp(
        config.confidence_base + len(evidence) * config.confidence_per_evidence,
        high=config.confidence_cap,
    )
    return Opportunity(
        category=category,
        label=config.label_for(category),
        score=score,
        severity=severity,
        confidence=confidence,
        evidence=tuple(evidence),
        business_impact=config.impact_for(category),
        implementation_effort=config.effort_for(category),
        recommended_services=config.services_for(category),
    )


def has_website(signals: ScoringInputs) -> bool:
    return bool((signals.website_url or "").strip())


def fetch_ok(signals: ScoringInputs) -> bool:
    return bool(signals.fetch_ok)


def platform(signals: ScoringInputs) -> str:
    extracted = signals.extracted if isinstance(signals.extracted, dict) else {}
    return safe_lower(extracted.get("platform"))


def complexity(signals: ScoringInputs) -> str:
    extracted = signals.extracted if isinstance(signals.extracted, dict) else {}
    return safe_lower(extracted.get("complexity"))


def load_speed(signals: ScoringInputs) -> str:
    extracted = signals.extracted if isinstance(signals.extracted, dict) else {}
    return safe_lower(extracted.get("load_speed"))


def extracted_field(signals: ScoringInputs, key: str) -> Any:
    extracted = signals.extracted if isinstance(signals.extracted, dict) else {}
    return extracted.get(key)


def dimension_score(lead_score: Optional[LeadScore], name: str) -> int:
    if lead_score is None:
        return 0
    return int(lead_score.dimension_scores.get(name) or 0)


def seo_audit(signals: ScoringInputs) -> dict[str, Any]:
    return signals.seo_audit if isinstance(signals.seo_audit, dict) else {}


def visual_audit(signals: ScoringInputs) -> dict[str, Any]:
    return signals.visual_audit if isinstance(signals.visual_audit, dict) else {}


def visual_int(audit: dict[str, Any], key: str) -> int:
    return as_int(audit.get(key))


def visual_pages(audit: dict[str, Any]) -> list[dict[str, Any]]:
    return [page for page in (audit.get("pages") or []) if isinstance(page, dict)]


def audit_int(audit: dict[str, Any], key: str) -> int:
    return as_int(audit.get(key))


def audit_pages(audit: dict[str, Any]) -> list[dict[str, Any]]:
    return [page for page in (audit.get("pages") or []) if isinstance(page, dict)]


def html_pages(audit: dict[str, Any]) -> list[dict[str, Any]]:
    return [page for page in audit_pages(audit) if as_int(page.get("html_available"))]


def pages_without_viewport(audit: dict[str, Any]) -> int:
    return sum(1 for page in html_pages(audit) if not as_int(page.get("viewport_present")))


def analytics_detected(detections: Optional[list[dict[str, Any]]]) -> bool:
    names = detection_names(detections)
    categories = detection_categories(detections)
    return bool(names & ANALYTICS_NAMES or "analytics" in categories)


def ecommerce_detected(signals: ScoringInputs) -> bool:
    names = detection_names(signals.detections)
    categories = detection_categories(signals.detections)
    return (
        platform(signals) in ECOMMERCE_PLATFORMS
        or bool(names & ECOMMERCE_NAMES)
        or bool(categories & {"shopping", "payment"})
    )


def hosting_cdn_detected(signals: ScoringInputs) -> bool:
    return "hosting" in detection_categories(signals.detections)


def modern_frontend_detected(signals: ScoringInputs) -> bool:
    from src.scoring.rules import MODERN_FRAMEWORKS

    names = detection_names(signals.detections)
    return platform(signals) in MODERN_FRAMEWORKS or bool(names & MODERN_FRAMEWORKS)


def responsive_framework_detected(signals: ScoringInputs) -> bool:
    return bool(detection_names(signals.detections) & RESPONSIVE_FRAMEWORKS)


def legacy_library_detected(signals: ScoringInputs) -> bool:
    names = detection_names(signals.detections)
    categories = detection_categories(signals.detections)
    return bool(names & LEGACY_LIBRARIES) or "libraries" in categories


def legacy_platform(signals: ScoringInputs) -> bool:
    from src.scoring.rules import LEGACY_CMS

    return platform(signals) in LEGACY_CMS
