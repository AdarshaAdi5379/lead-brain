from __future__ import annotations

from typing import Optional

from src.scoring.base import DimensionResult, ScoringInputs
from src.scoring.config import ScoringConfig, default_config
from src.scoring.rules import (
    as_int,
    clamp,
    contact_clues,
    detection_categories,
    detection_names,
    has_about_page,
    has_contact_page,
    has_services_page,
    has_social_links,
    has_text,
    is_https_url,
    is_legacy_platform,
    is_modern_platform,
    page_labels,
    safe_lower,
    safe_str,
)


def _extracted(inputs: ScoringInputs) -> dict:
    return inputs.extracted if isinstance(inputs.extracted, dict) else {}


def _platform(inputs: ScoringInputs) -> str:
    return safe_lower(_extracted(inputs).get("platform"))


def _load_speed(inputs: ScoringInputs) -> str:
    return safe_lower(_extracted(inputs).get("load_speed"))


def _phone(inputs: ScoringInputs) -> str:
    return safe_str(_extracted(inputs).get("phone"))


def _email(inputs: ScoringInputs) -> str:
    return safe_str(_extracted(inputs).get("email"))


def discovery_quality(inputs: ScoringInputs, config: Optional[ScoringConfig] = None) -> DimensionResult:
    config = config or default_config()
    """How solid the discovery record is (identity, location, source)."""
    reasons: list[str] = []
    points = 0

    if has_text(inputs.category):
        points += config.discovery_category_points
        reasons.append(f"Business category present (+{config.discovery_category_points})")
    if has_text(inputs.city) or has_text(inputs.state):
        points += config.discovery_location_points
        reasons.append(f"Location present (+{config.discovery_location_points})")
    if has_text(inputs.business_name):
        points += config.discovery_identity_points
        reasons.append(f"Business identity present (+{config.discovery_identity_points})")
    if has_text(inputs.source) or has_text(inputs.osm_id):
        points += config.discovery_source_points
        reasons.append(f"Structured source present: {safe_str(inputs.source) or 'OSM'} (+{config.discovery_source_points})")
    if has_text(inputs.website_url):
        points += config.discovery_website_points
        reasons.append(f"Website present (+{config.discovery_website_points})")
    if has_text(inputs.address):
        points += config.discovery_address_points
        reasons.append(f"Street address present (+{config.discovery_address_points})")
    if _phone(inputs) or _email(inputs):
        points += config.discovery_contact_points
        reasons.append(f"Contact data present (+{config.discovery_contact_points})")

    if not reasons:
        reasons.append("No discovery signals available")

    return DimensionResult(name="discovery_quality", score=clamp(points), reasons=tuple(reasons))


def contactability(inputs: ScoringInputs, config: Optional[ScoringConfig] = None) -> DimensionResult:
    config = config or default_config()
    """How reachable the business is across channels."""
    reasons: list[str] = []
    points = 0

    if has_text(_email(inputs)):
        points += config.contact_email_points
        reasons.append(f"Email address found (+{config.contact_email_points})")
    if has_text(_phone(inputs)):
        points += config.contact_phone_points
        reasons.append(f"Phone number found (+{config.contact_phone_points})")
    if has_contact_page(inputs.crawl):
        points += config.contact_page_points
        reasons.append(f"Contact page found (+{config.contact_page_points})")
    if has_text(inputs.website_url):
        points += config.contact_website_points
        reasons.append(f"Website present (+{config.contact_website_points})")
    clues = contact_clues(inputs.crawl)
    if clues:
        points += config.contact_clues_points
        reasons.append(f"Contact details extracted from site ({len(clues)} clue(s)) (+{config.contact_clues_points})")
    if has_text(inputs.address):
        points += config.contact_address_points
        reasons.append(f"Street address present (+{config.contact_address_points})")
    if has_social_links(inputs.crawl):
        points += config.contact_social_points
        reasons.append(f"Social links found (+{config.contact_social_points})")

    if not reasons:
        reasons.append("No contact channels found")

    return DimensionResult(name="contactability", score=clamp(points), reasons=tuple(reasons))


def technical_health(inputs: ScoringInputs, config: Optional[ScoringConfig] = None) -> DimensionResult:
    config = config or default_config()
    """Reachability, platform maturity and page-quality signals."""
    reasons: list[str] = []
    points = 0

    if not has_text(inputs.website_url):
        reasons.append("No website to assess")
        return DimensionResult(name="technical_health", score=0, reasons=tuple(reasons))

    fetch_ok = inputs.fetch_ok if inputs.fetch_ok is not None else True
    if fetch_ok:
        points += config.tech_fetch_ok_points
        reasons.append(f"Site reachable (+{config.tech_fetch_ok_points})")
    else:
        points -= config.tech_broken_penalty
        reasons.append(f"Site broken or blocked (−{config.tech_broken_penalty})")

    platform = _platform(inputs)
    if platform and platform != "unknown":
        points += config.tech_platform_known_points
        reasons.append(f"Platform detected: {platform} (+{config.tech_platform_known_points})")

    names = detection_names(inputs.detections)
    categories = detection_categories(inputs.detections)
    if is_modern_platform(platform, names):
        points += config.tech_modern_points
        reasons.append(f"Modern framework signal (+{config.tech_modern_points})")
    elif is_legacy_platform(platform):
        points += config.tech_legacy_points
        reasons.append(f"Standard CMS/platform: {platform} (+{config.tech_legacy_points})")

    load_speed = _load_speed(inputs)
    if load_speed in {"fast", "medium"}:
        points += config.tech_fast_points
        reasons.append(f"Load speed: {load_speed} (+{config.tech_fast_points})")

    if categories:
        points += config.tech_detections_points
        reasons.append(f"Technology fingerprints present ({len(categories)} categor{'y' if len(categories) == 1 else 'ies'}) (+{config.tech_detections_points})")

    if not reasons:
        reasons.append("No technical signals available")

    return DimensionResult(name="technical_health", score=clamp(points), reasons=tuple(reasons))


def seo_health(inputs: ScoringInputs, config: Optional[ScoringConfig] = None) -> DimensionResult:
    config = config or default_config()
    """Deterministic SEO audit results (or explicit unknowns when missing)."""
    if not has_text(inputs.website_url):
        return DimensionResult(
            name="seo_health",
            score=config.seo_no_website_score,
            reasons=("No website to audit",),
        )

    audit = inputs.seo_audit
    if not audit:
        return DimensionResult(
            name="seo_health",
            score=config.seo_unverifiable_score,
            reasons=("Site could not be crawled; SEO unverifiable",),
        )

    reasons: list[str] = []
    points = clamp(as_int(audit.get("site_score")))
    reasons.append(f"Deterministic site SEO score: {points}/100")

    if audit.get("sitemap_detected"):
        points = clamp(points + config.seo_sitemap_points)
        reasons.append(f"Sitemap detected (+{config.seo_sitemap_points})")
    if audit.get("robots_txt_detected"):
        points = clamp(points + config.seo_robots_points)
        reasons.append(f"robots.txt detected (+{config.seo_robots_points})")
    if as_int(audit.get("pages_with_duplicate_titles")) > 0:
        points = clamp(points - config.seo_duplicate_titles_penalty)
        reasons.append(f"Duplicate titles on {as_int(audit.get('pages_with_duplicate_titles'))} page(s) (−{config.seo_duplicate_titles_penalty})")
    if as_int(audit.get("pages_with_duplicate_descriptions")) > 0:
        points = clamp(points - config.seo_duplicate_descriptions_penalty)
        reasons.append(f"Duplicate meta descriptions on {as_int(audit.get('pages_with_duplicate_descriptions'))} page(s) (−{config.seo_duplicate_descriptions_penalty})")
    html_pages = as_int(audit.get("html_pages"))
    if html_pages > 0 and as_int(audit.get("pages_with_json_ld")) == 0:
        points = clamp(points - config.seo_missing_structured_data_penalty)
        reasons.append(f"No structured data (JSON-LD) detected (−{config.seo_missing_structured_data_penalty})")
    if as_int(audit.get("pages_with_thin_content")) > 0:
        points = clamp(points - config.seo_thin_content_penalty)
        reasons.append(f"Thin content on {as_int(audit.get('pages_with_thin_content'))} page(s) (−{config.seo_thin_content_penalty})")
    if as_int(audit.get("pages_with_images_missing_alt")) > 0:
        points = clamp(points - config.seo_missing_alt_penalty)
        reasons.append(f"Images missing alt text on {as_int(audit.get('pages_with_images_missing_alt'))} page(s) (−{config.seo_missing_alt_penalty})")

    return DimensionResult(name="seo_health", score=clamp(points), reasons=tuple(reasons))


def _homepage_word_count(inputs: ScoringInputs) -> int:
    audit = inputs.seo_audit
    if audit:
        for page in audit.get("pages") or []:
            if isinstance(page, dict) and safe_lower(page.get("page_type")) == "home":
                return as_int(page.get("word_count"))
    crawl = inputs.crawl
    if crawl:
        for page in crawl.get("pages") or []:
            if isinstance(page, dict) and safe_lower(page.get("label")) in {"home", "homepage"}:
                return len(safe_str(page.get("text")).split())
    return 0


def content_strength(inputs: ScoringInputs, config: Optional[ScoringConfig] = None) -> DimensionResult:
    config = config or default_config()
    """Meaningful content on key pages (services, about, homepage text)."""
    reasons: list[str] = []
    points = 0

    words = _homepage_word_count(inputs)
    target = config.content_homepage_words_target
    if words >= target:
        points += config.content_homepage_points
        reasons.append(f"Substantial homepage text ({words} words) (+{config.content_homepage_points})")
    elif words > 0:
        scaled = clamp(words / target * config.content_homepage_points)
        if scaled >= 5:
            points += scaled
            reasons.append(f"Homepage has {words} words (partial credit +{scaled})")
        else:
            points += scaled
            reasons.append(f"Homepage is thin ({words} words)")

    if has_services_page(inputs.crawl):
        points += config.content_services_points
        reasons.append(f"Services/products page found (+{config.content_services_points})")
    if has_about_page(inputs.crawl):
        points += config.content_about_points
        reasons.append(f"About page found (+{config.content_about_points})")

    page_count = len(page_labels(inputs.crawl))
    if page_count >= 3:
        points += config.content_multi_page_points
        reasons.append(f"Multi-page site ({page_count} pages) (+{config.content_multi_page_points})")

    merged_text = safe_str((inputs.crawl or {}).get("merged_text"))
    if len(merged_text) >= config.content_text_chars_target:
        points += config.content_text_points
        reasons.append(f"Substantial site content (~{len(merged_text)} chars) (+{config.content_text_points})")

    if not reasons:
        reasons.append("No site content available to assess")

    return DimensionResult(name="content_strength", score=clamp(points), reasons=tuple(reasons))


def trust_professionalism(inputs: ScoringInputs, config: Optional[ScoringConfig] = None) -> DimensionResult:
    config = config or default_config()
    """HTTPS, branding, contact visibility and abandonment indicators."""
    reasons: list[str] = []
    points = 0

    if not has_text(inputs.website_url):
        reasons.append("No website to assess")
        return DimensionResult(name="trust_professionalism", score=0, reasons=tuple(reasons))

    if is_https_url(inputs.website_url):
        points += config.trust_https_points
        reasons.append(f"HTTPS enabled (+{config.trust_https_points})")
    else:
        reasons.append("No HTTPS on website")

    audit = inputs.seo_audit or {}
    branded = has_text(inputs.business_name) and as_int(audit.get("pages_with_title")) > 0
    if branded:
        points += config.trust_branding_points
        reasons.append(f"Consistent branding (business name + page titles) (+{config.trust_branding_points})")
    if has_text(_email(inputs)) or has_text(_phone(inputs)) or has_contact_page(inputs.crawl) or contact_clues(inputs.crawl):
        points += config.trust_contact_visible_points
        reasons.append(f"Contact information visible (+{config.trust_contact_visible_points})")

    platform = _platform(inputs)
    names = detection_names(inputs.detections)
    if is_modern_platform(platform, names):
        points += config.trust_modern_points
        reasons.append(f"Modern framework signal (+{config.trust_modern_points})")

    if has_social_links(inputs.crawl) or as_int(audit.get("pages_with_json_ld")) > 0:
        points += config.trust_social_meta_points
        reasons.append(f"Structured data or social presence detected (+{config.trust_social_meta_points})")

    html_pages = as_int(audit.get("html_pages"))
    if html_pages > 0:
        points += config.trust_live_content_points
        reasons.append(f"Live site content verified ({html_pages} page(s)) (+{config.trust_live_content_points})")
        if as_int(audit.get("pages_with_noindex")) >= html_pages:
            points = clamp(points - config.trust_noindex_penalty)
            reasons.append(f"Whole site noindexed (−{config.trust_noindex_penalty})")

    if not reasons:
        reasons.append("No trust signals available")

    return DimensionResult(name="trust_professionalism", score=clamp(points), reasons=tuple(reasons))


def outreach_potential(
    inputs: ScoringInputs,
    config: Optional[ScoringConfig],
    dimension_scores: dict[str, int],
) -> DimensionResult:
    config = config or default_config()
    """Bias dimension: contactable leads with visible room for improvement."""
    reasons: list[str] = []
    points = 0

    if dimension_scores.get("contactability", 0) >= config.outreach_contactable_min:
        points += config.outreach_contactable_points
        reasons.append(f"Business is contactable (+{config.outreach_contactable_points})")
    has_known_business = has_text(inputs.business_name) or has_text(inputs.category) or has_text(inputs.website_url)
    if has_known_business and (
        dimension_scores.get("technical_health", 100) < config.outreach_improvement_max
        or dimension_scores.get("seo_health", 100) < config.outreach_improvement_max
    ):
        points += config.outreach_improvement_points
        reasons.append(f"Clear improvement opportunity (weak website signals) (+{config.outreach_improvement_points})")
    if has_text(inputs.business_name) and has_text(inputs.category) and (
        has_text(inputs.city) or has_text(inputs.state)
    ):
        points += config.outreach_active_points
        reasons.append(f"Real, active business presence (+{config.outreach_active_points})")
    if has_text(inputs.website_url) and (has_services_page(inputs.crawl) or has_text(inputs.category)):
        points += config.outreach_service_site_points
        reasons.append(f"Service business with a website (+{config.outreach_service_site_points})")

    if not reasons:
        reasons.append("Limited outreach signals available")

    return DimensionResult(name="outreach_potential", score=clamp(points), reasons=tuple(reasons))
