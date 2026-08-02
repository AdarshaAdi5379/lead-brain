from __future__ import annotations

from typing import Optional

from src.opportunities.base import Opportunity
from src.opportunities.config import OpportunityConfig
from src.opportunities.rules import (
    analytics_detected,
    audit_int,
    audit_pages,
    build_opportunity,
    complexity,
    dimension_score,
    ecommerce_detected,
    extracted_field,
    fetch_ok,
    has_about_page,
    has_contact_page,
    has_services_page,
    has_text,
    has_website,
    hosting_cdn_detected,
    html_pages,
    legacy_library_detected,
    legacy_platform,
    load_speed,
    modern_frontend_detected,
    pages_without_viewport,
    platform,
    responsive_framework_detected,
    seo_audit,
)
from src.scoring.base import LeadScore, ScoringInputs
from src.scoring.rules import is_https_url

# Detectors are independent, deterministic functions over already-collected
# signals. They never perform network requests, never call the LLM, and never
# touch the database. Adding a new detector = write a function here and
# register it in registry.py.


def detect_website_redesign(
    signals: ScoringInputs,
    lead_score: Optional[LeadScore],
    config: OpportunityConfig,
) -> Optional[Opportunity]:
    if not has_website(signals):
        return None
    audit = seo_audit(signals)
    points = 0
    evidence: list[str] = []

    if legacy_platform(signals):
        points += config.redesign_legacy_platform_points
        evidence.append(f"Site runs on a legacy platform ({platform(signals)})")

    trust = dimension_score(lead_score, "trust_professionalism")
    if 0 < trust < config.redesign_low_trust_threshold:
        points += config.redesign_low_trust_points
        evidence.append(f"Weak trust/professionalism signals ({trust}/100)")

    seo_score = dimension_score(lead_score, "seo_health")
    if 0 < seo_score < config.redesign_low_seo_threshold:
        points += config.redesign_low_seo_points
        evidence.append(f"Poor SEO health ({seo_score}/100)")

    content = dimension_score(lead_score, "content_strength")
    if 0 < content < config.redesign_low_content_threshold:
        points += config.redesign_low_content_points
        evidence.append(f"Thin content profile ({content}/100)")

    duplicates = audit_int(audit, "pages_with_duplicate_titles")
    if duplicates > 0:
        points += config.redesign_duplicate_titles_points
        evidence.append(f"{duplicates} page(s) share duplicate title tags")

    return build_opportunity("website_redesign", points, evidence, config)


def detect_seo_improvement(
    signals: ScoringInputs,
    lead_score: Optional[LeadScore],
    config: OpportunityConfig,
) -> Optional[Opportunity]:
    if not has_website(signals):
        return None
    audit = seo_audit(signals)
    points = 0
    evidence: list[str] = []

    html = audit_int(audit, "html_pages")
    if html > 0:
        with_title = audit_int(audit, "pages_with_title")
        missing = max(0, html - with_title)
        if missing > 0:
            points += min(missing * config.seo_missing_title_each, config.seo_missing_title_max)
            evidence.append(f"{missing}/{html} page(s) missing title tags")
        with_meta = audit_int(audit, "pages_with_meta_description")
        if with_meta < html:
            points += config.seo_missing_meta_points
            evidence.append(f"{html - with_meta}/{html} page(s) missing meta descriptions")

    with_json_ld = audit_int(audit, "pages_with_json_ld")
    if html > 0 and with_json_ld == 0:
        points += config.seo_missing_structured_data_points
        evidence.append("No structured data (JSON-LD) detected on any page")

    duplicates = audit_int(audit, "pages_with_duplicate_titles")
    if duplicates > 0:
        points += config.seo_duplicate_titles_points
        evidence.append(f"{duplicates} page(s) share duplicate title tags")

    if not audit_int(audit, "sitemap_detected"):
        points += config.seo_no_sitemap_points
        evidence.append("No XML sitemap detected")
    if not audit_int(audit, "robots_txt_detected"):
        points += config.seo_no_robots_points
        evidence.append("No robots.txt detected")

    thin = audit_int(audit, "pages_with_thin_content")
    if thin > 0:
        points += config.seo_thin_content_points
        evidence.append(f"{thin} page(s) with thin content")

    site_score = audit_int(audit, "site_score")
    if site_score > 0 and site_score < config.seo_low_site_score_threshold:
        points += config.seo_low_site_score_base
        evidence.append(f"Low overall SEO score ({site_score}/100)")

    return build_opportunity("seo_improvement", points, evidence, config)


def detect_performance_optimization(
    signals: ScoringInputs,
    lead_score: Optional[LeadScore],
    config: OpportunityConfig,
) -> Optional[Opportunity]:
    if not has_website(signals):
        return None
    points = 0
    evidence: list[str] = []

    speed = load_speed(signals)
    if speed == "slow":
        points += config.perf_slow_load_points
        evidence.append("Site loads slowly")
    elif speed == "medium":
        points += config.perf_medium_load_points
        evidence.append("Site load speed is average")

    if legacy_library_detected(signals):
        points += config.perf_jquery_points
        evidence.append("Legacy JavaScript library (jQuery) detected")

    audit = seo_audit(signals)
    missing_alt = audit_int(audit, "pages_with_images_missing_alt")
    if missing_alt > 0:
        points += config.perf_image_heavy_points
        evidence.append(f"{missing_alt} page(s) with images that are not optimized for alt text")

    if not hosting_cdn_detected(signals):
        points += config.perf_no_cdn_points
        evidence.append("No CDN or hosting provider detected")

    return build_opportunity("performance_optimization", points, evidence, config)


def detect_accessibility_improvement(
    signals: ScoringInputs,
    lead_score: Optional[LeadScore],
    config: OpportunityConfig,
) -> Optional[Opportunity]:
    if not has_website(signals):
        return None
    audit = seo_audit(signals)
    points = 0
    evidence: list[str] = []

    missing_alt = audit_int(audit, "pages_with_images_missing_alt")
    if missing_alt > 0:
        points += min(
            config.a11y_missing_alt_base + missing_alt * config.a11y_missing_alt_each,
            config.a11y_missing_alt_max,
        )
        evidence.append(f"{missing_alt} page(s) contain images missing alt text")

    html = audit_int(audit, "html_pages")
    if html > 0:
        with_h1 = audit_int(audit, "pages_with_h1")
        if with_h1 < html:
            points += config.a11y_missing_h1_points
            evidence.append(f"{html - with_h1}/{html} page(s) missing a single H1 heading")
        multiple = audit_int(audit, "pages_with_multiple_h1")
        if multiple > 0:
            points += config.a11y_multiple_h1_points
            evidence.append(f"{multiple} page(s) use multiple H1 headings")

    without_viewport = pages_without_viewport(audit)
    if without_viewport > 0:
        points += config.a11y_no_viewport_points
        evidence.append(f"{without_viewport} page(s) missing a mobile viewport meta tag")

    return build_opportunity("accessibility_improvement", points, evidence, config)


def detect_content_improvement(
    signals: ScoringInputs,
    lead_score: Optional[LeadScore],
    config: OpportunityConfig,
) -> Optional[Opportunity]:
    if not has_website(signals):
        return None
    audit = seo_audit(signals)
    points = 0
    evidence: list[str] = []

    thin = audit_int(audit, "pages_with_thin_content")
    if thin > 0:
        points += config.content_thin_points
        evidence.append(f"{thin} page(s) with thin content")

    content = dimension_score(lead_score, "content_strength")
    if 0 < content < config.content_low_strength_threshold:
        points += config.content_low_strength_points
        evidence.append(f"Weak overall content ({content}/100)")

    pages = audit_pages(audit)
    types = {str(page.get("page_type") or "").lower() for page in pages if page.get("page_type")}
    labels = {str(page.get("label") or "").lower() for page in pages if page.get("label")}
    has_services = bool(types & {"services", "product"}) or bool(labels & {"services", "products"})
    has_about = bool(types & {"about"}) or bool(labels & {"about", "aboutus"})

    if not has_services:
        points += config.content_no_services_points
        evidence.append("No services/products page found in the crawl")
    if not has_about:
        points += config.content_no_about_points
        evidence.append("No about page found in the crawl")

    return build_opportunity("content_improvement", points, evidence, config)


def detect_brand_refresh(
    signals: ScoringInputs,
    lead_score: Optional[LeadScore],
    config: OpportunityConfig,
) -> Optional[Opportunity]:
    if not has_website(signals):
        return None
    audit = seo_audit(signals)
    points = 0
    evidence: list[str] = []

    trust = dimension_score(lead_score, "trust_professionalism")
    if 0 < trust < config.brand_low_trust_threshold:
        points += config.brand_low_trust_points
        evidence.append(f"Low trust/professionalism signals ({trust}/100)")

    if legacy_platform(signals):
        points += config.brand_legacy_points
        evidence.append(f"Outdated platform in use ({platform(signals)})")

    pages = html_pages(audit)
    if pages and not any(
        int(page.get("og_title_present") or 0) or int(page.get("twitter_card_present") or 0)
        for page in pages
    ):
        points += config.brand_no_social_points
        evidence.append("No social sharing meta tags (Open Graph/Twitter) on any page")

    if audit_int(audit, "pages_with_thin_content") > 0:
        points += config.brand_thin_points
        evidence.append("Thin content contributes to a weak brand impression")

    return build_opportunity("brand_refresh", points, evidence, config)


def detect_technical_modernization(
    signals: ScoringInputs,
    lead_score: Optional[LeadScore],
    config: OpportunityConfig,
) -> Optional[Opportunity]:
    if not has_website(signals):
        return None
    points = 0
    evidence: list[str] = []

    if legacy_library_detected(signals):
        points += config.techmod_jquery_points
        evidence.append("Legacy JavaScript library (jQuery) detected")

    if legacy_platform(signals):
        points += config.techmod_legacy_cms_points
        evidence.append(f"Legacy CMS in use ({platform(signals)})")

    if not modern_frontend_detected(signals):
        points += config.techmod_no_modern_points
        evidence.append("No modern frontend framework detected")

    if complexity(signals) == "basic":
        points += config.techmod_basic_complexity_points
        evidence.append("Site complexity rated basic")

    if platform(signals) in ("", "unknown"):
        points += config.techmod_unknown_platform_points
        evidence.append("Site platform could not be determined")

    return build_opportunity("technical_modernization", points, evidence, config)


def detect_mobile_optimization(
    signals: ScoringInputs,
    lead_score: Optional[LeadScore],
    config: OpportunityConfig,
) -> Optional[Opportunity]:
    if not has_website(signals):
        return None
    points = 0
    evidence: list[str] = []

    without_viewport = pages_without_viewport(seo_audit(signals))
    if without_viewport > 0:
        points += config.mobile_no_viewport_points
        evidence.append(f"{without_viewport} page(s) missing a mobile viewport meta tag")

    if not responsive_framework_detected(signals):
        points += config.mobile_no_responsive_framework_points
        evidence.append("No responsive framework (e.g. Bootstrap, Tailwind) detected")

    if load_speed(signals) == "slow":
        points += config.mobile_slow_points
        evidence.append("Slow load speed hurts mobile experience")

    if complexity(signals) == "basic":
        points += config.mobile_basic_points
        evidence.append("Basic site likely lacks dedicated mobile layouts")

    return build_opportunity("mobile_optimization", points, evidence, config)


def detect_analytics_setup(
    signals: ScoringInputs,
    lead_score: Optional[LeadScore],
    config: OpportunityConfig,
) -> Optional[Opportunity]:
    if not has_website(signals) or not fetch_ok(signals):
        return None
    if analytics_detected(signals.detections):
        return None
    points = config.analytics_missing_points
    evidence = [
        "No analytics platform detected (no Google Analytics, GTM, Clarity or similar)"
    ]
    if has_contact_page(signals.crawl):
        points += config.analytics_contact_page_points
        evidence.append("Site has a contact funnel that cannot be measured")
    if has_services_page(signals.crawl):
        points += config.analytics_services_page_points
        evidence.append("Service pages exist without conversion tracking")

    return build_opportunity("analytics_setup", points, evidence, config)


def detect_security_improvement(
    signals: ScoringInputs,
    lead_score: Optional[LeadScore],
    config: OpportunityConfig,
) -> Optional[Opportunity]:
    if not has_website(signals):
        return None
    points = 0
    evidence: list[str] = []

    if not is_https_url(signals.website_url):
        points += config.security_no_https_points
        evidence.append(f"Site is not served over HTTPS ({signals.website_url})")

    mixed = audit_int(seo_audit(signals), "pages_with_mixed_content")
    if mixed > 0:
        points += config.security_mixed_content_points
        evidence.append(f"{mixed} page(s) contain mixed content (insecure HTTP resources)")

    return build_opportunity("security_improvement", points, evidence, config)


def detect_local_seo(
    signals: ScoringInputs,
    lead_score: Optional[LeadScore],
    config: OpportunityConfig,
) -> Optional[Opportunity]:
    if not has_website(signals):
        return None
    audit = seo_audit(signals)
    points = 0
    evidence: list[str] = []

    has_location = bool((signals.city or "").strip() or (signals.state or "").strip() or (signals.address or "").strip())
    if has_location:
        points += config.local_has_location_points
        evidence.append("Local business with a city/state address")

    html = audit_int(audit, "html_pages")
    if html > 0 and audit_int(audit, "pages_with_json_ld") == 0:
        points += config.local_no_structured_data_points
        evidence.append("No LocalBusiness structured data detected")

    if not audit_int(audit, "sitemap_detected"):
        points += config.local_no_sitemap_points
        evidence.append("No XML sitemap for local indexing")

    if not audit_int(audit, "robots_txt_detected"):
        points += config.local_no_robots_points
        evidence.append("No robots.txt found")

    if has_contact_page(signals.crawl):
        points += config.local_has_contact_points
        evidence.append("Contact page present, ready to receive local enquiries")

    return build_opportunity("local_seo", points, evidence, config)


def detect_contact_funnel_improvement(
    signals: ScoringInputs,
    lead_score: Optional[LeadScore],
    config: OpportunityConfig,
) -> Optional[Opportunity]:
    if not has_website(signals):
        return None
    points = 0
    evidence: list[str] = []

    if not has_contact_page(signals.crawl):
        points += config.funnel_no_contact_page_points
        evidence.append("No contact page found in the crawl")

    phone = extracted_field(signals, "phone")
    email = extracted_field(signals, "email")
    if not has_text(phone):
        points += config.funnel_no_phone_points
        evidence.append("No phone number found on the site")
    if not has_text(email):
        points += config.funnel_no_email_points
        evidence.append("No email address found on the site")

    clues = signals.crawl.get("contact_clues") if isinstance(signals.crawl, dict) else []
    if not clues:
        points += config.funnel_no_clues_points
        evidence.append("No contact clues (form/CTA) detected in the crawl")

    return build_opportunity("contact_funnel_improvement", points, evidence, config)


def detect_conversion_optimization(
    signals: ScoringInputs,
    lead_score: Optional[LeadScore],
    config: OpportunityConfig,
) -> Optional[Opportunity]:
    if not has_website(signals):
        return None
    audit = seo_audit(signals)
    points = 0
    evidence: list[str] = []

    email = extracted_field(signals, "email")
    has_form_signal = has_contact_page(signals.crawl) or bool(
        signals.crawl.get("contact_clues") if isinstance(signals.crawl, dict) else []
    )
    if not has_form_signal:
        points += config.cro_no_form_points
        evidence.append("No contact form or obvious conversion element detected")

    if not has_text(email):
        points += config.cro_no_email_points
        evidence.append("No email capture point found")

    if audit_int(audit, "pages_with_thin_content") > 0:
        points += config.cro_thin_points
        evidence.append("Thin pages limit trust during conversion")

    if complexity(signals) == "basic":
        points += config.cro_basic_points
        evidence.append("Basic site lacks structured conversion paths")

    return build_opportunity("conversion_optimization", points, evidence, config)


def detect_hosting_upgrade(
    signals: ScoringInputs,
    lead_score: Optional[LeadScore],
    config: OpportunityConfig,
) -> Optional[Opportunity]:
    if not has_website(signals) or not fetch_ok(signals):
        return None
    points = 0
    evidence: list[str] = []

    if load_speed(signals) == "slow":
        points += config.hosting_slow_points
        evidence.append("Slow load speed suggests limited hosting capacity")

    if not hosting_cdn_detected(signals):
        points += config.hosting_no_cdn_points
        evidence.append("No CDN or managed hosting provider detected")

    if complexity(signals) == "basic":
        points += config.hosting_basic_points
        evidence.append("Basic site architecture offers headroom for an upgrade")

    return build_opportunity("hosting_upgrade", points, evidence, config)


def detect_ecommerce_optimization(
    signals: ScoringInputs,
    lead_score: Optional[LeadScore],
    config: OpportunityConfig,
) -> Optional[Opportunity]:
    if not has_website(signals):
        return None
    if not ecommerce_detected(signals):
        return None
    audit = seo_audit(signals)
    points = 0
    evidence = [
        f"E-commerce signals detected ({platform(signals) or 'shopping/payment stack'})"
    ]

    if not analytics_detected(signals.detections):
        points += config.ecom_no_analytics_points
        evidence.append("No analytics or conversion tracking detected")

    if not has_contact_page(signals.crawl):
        points += config.ecom_no_contact_points
        evidence.append("No contact page to support post-purchase support")

    if load_speed(signals) == "slow":
        points += config.ecom_performance_points
        evidence.append("Slow load speed directly impacts checkout conversion")

    if audit_int(audit, "pages_with_json_ld") == 0:
        points += config.ecom_no_structured_data_points
        evidence.append("No product structured data detected")

    return build_opportunity("ecommerce_optimization", points, evidence, config)


def detect_maintenance_opportunity(
    signals: ScoringInputs,
    lead_score: Optional[LeadScore],
    config: OpportunityConfig,
) -> Optional[Opportunity]:
    if not has_website(signals):
        return None
    audit = seo_audit(signals)
    points = 0
    evidence: list[str] = []

    if legacy_platform(signals):
        points += config.maint_legacy_cms_points
        evidence.append(f"Active site on {platform(signals)} needs ongoing maintenance")

    if not audit_int(audit, "sitemap_detected") or not audit_int(audit, "robots_txt_detected"):
        points += config.maint_site_hygiene_points
        evidence.append("Site hygiene gaps (missing sitemap/robots.txt)")

    html = audit_int(audit, "html_pages")
    minor_issues = 0
    if html > 0 and audit_int(audit, "pages_with_title") < html:
        minor_issues += 1
    if html > 0 and audit_int(audit, "pages_with_meta_description") < html:
        minor_issues += 1
    if audit_int(audit, "pages_with_noindex") > 0:
        minor_issues += 1
    if minor_issues >= 2:
        points += config.maint_minor_issues_points
        evidence.append(f"{minor_issues} categories of minor technical issues present")

    if audit_int(audit, "pages_with_thin_content") > 0:
        points += config.maint_thin_points
        evidence.append("Thin content needs regular refresh")

    return build_opportunity("maintenance_opportunity", points, evidence, config)
