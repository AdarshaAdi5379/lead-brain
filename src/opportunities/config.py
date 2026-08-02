from __future__ import annotations

from dataclasses import dataclass, field

from src.opportunities.base import CATEGORY_LABELS


@dataclass(frozen=True)
class OpportunityConfig:
    """Every tunable number used by the opportunity engine.

    Adjusting point values, thresholds, service recommendations or the
    impact/effort maps here is the supported way to tune the model; the
    detectors themselves stay read-only over this config.
    """

    # (minimum_score, severity) bands, evaluated in order. Scores below the
    # lowest band are "Ignore" and do not produce an opportunity.
    severity_bands: tuple[tuple[int, str], ...] = (
        (90, "Critical"),
        (70, "High"),
        (50, "Medium"),
        (30, "Low"),
    )

    # Opportunities scoring below this are dropped entirely (band 0-29).
    min_detectable_score: int = 30

    # Lead-level opportunity priority bands (revenue potential).
    priority_bands: tuple[tuple[int, str], ...] = (
        (75, "High Revenue Potential"),
        (55, "Medium Revenue Potential"),
        (30, "Low Revenue Potential"),
    )
    minimal_priority_label: str = "Minimal Opportunity"

    # Confidence is derived from the number of independent signals fired.
    confidence_base: int = 45
    confidence_per_evidence: int = 12
    confidence_cap: int = 95

    # --- website_redesign ---
    redesign_legacy_platform_points: int = 40
    redesign_low_trust_points: int = 20
    redesign_low_seo_points: int = 20
    redesign_low_content_points: int = 10
    redesign_duplicate_titles_points: int = 5
    redesign_clutter_points: int = 15
    redesign_weak_hierarchy_points: int = 10
    redesign_low_trust_threshold: int = 50
    redesign_low_seo_threshold: int = 40
    redesign_low_content_threshold: int = 50
    # Strong visual design reduces redesign urgency (subtracted from the points).
    redesign_strong_design_offset: int = 10

    # --- seo_improvement ---
    seo_missing_title_each: int = 6
    seo_missing_title_max: int = 30
    seo_missing_meta_points: int = 15
    seo_missing_structured_data_points: int = 10
    seo_duplicate_titles_points: int = 10
    seo_no_sitemap_points: int = 5
    seo_no_robots_points: int = 5
    seo_thin_content_points: int = 5
    seo_low_site_score_base: int = 10
    seo_low_site_score_threshold: int = 60

    # --- performance_optimization ---
    perf_slow_load_points: int = 30
    perf_medium_load_points: int = 10
    perf_jquery_points: int = 20
    perf_image_heavy_points: int = 10
    perf_no_cdn_points: int = 20

    # --- accessibility_improvement ---
    a11y_missing_alt_base: int = 30
    a11y_missing_alt_each: int = 10
    a11y_missing_alt_max: int = 60
    a11y_missing_h1_points: int = 20
    a11y_multiple_h1_points: int = 10
    a11y_no_viewport_points: int = 10

    # --- content_improvement ---
    content_thin_points: int = 25
    content_low_strength_points: int = 20
    content_no_services_points: int = 15
    content_no_about_points: int = 10
    content_low_strength_threshold: int = 50

    # --- brand_refresh ---
    brand_low_trust_points: int = 30
    brand_legacy_points: int = 25
    brand_no_social_points: int = 15
    brand_thin_points: int = 10
    brand_no_visual_identity_points: int = 15
    brand_low_trust_threshold: int = 50

    # --- technical_modernization ---
    techmod_jquery_points: int = 25
    techmod_legacy_cms_points: int = 25
    techmod_no_modern_points: int = 25
    techmod_basic_complexity_points: int = 10
    techmod_unknown_platform_points: int = 10

    # --- mobile_optimization ---
    mobile_no_viewport_points: int = 40
    mobile_no_responsive_framework_points: int = 25
    mobile_slow_points: int = 15
    mobile_basic_points: int = 10
    mobile_weak_layout_points: int = 20

    # --- analytics_setup ---
    analytics_missing_points: int = 60
    analytics_contact_page_points: int = 15
    analytics_services_page_points: int = 15

    # --- security_improvement ---
    security_no_https_points: int = 50
    security_mixed_content_points: int = 40

    # --- local_seo ---
    local_has_location_points: int = 20
    local_no_structured_data_points: int = 20
    local_no_sitemap_points: int = 15
    local_no_robots_points: int = 10
    local_has_contact_points: int = 15

    # --- contact_funnel_improvement ---
    funnel_no_contact_page_points: int = 30
    funnel_no_phone_points: int = 20
    funnel_no_email_points: int = 20
    funnel_no_clues_points: int = 10

    # --- conversion_optimization ---
    cro_no_form_points: int = 30
    cro_no_email_points: int = 20
    cro_thin_points: int = 15
    cro_basic_points: int = 15
    cro_weak_cta_points: int = 15

    # --- hosting_upgrade ---
    hosting_slow_points: int = 40
    hosting_no_cdn_points: int = 20
    hosting_basic_points: int = 10

    # --- ecommerce_optimization ---
    ecom_no_analytics_points: int = 30
    ecom_no_contact_points: int = 20
    ecom_performance_points: int = 20
    ecom_no_structured_data_points: int = 15

    # --- maintenance_opportunity ---
    maint_legacy_cms_points: int = 30
    maint_site_hygiene_points: int = 15
    maint_minor_issues_points: int = 20
    maint_thin_points: int = 10

    # Service recommendations and business impact/effort per category.
    service_mapping: dict[str, tuple[str, ...]] = field(
        default_factory=lambda: {
            "website_redesign": (
                "UI/UX Redesign",
                "Responsive Website Redesign",
                "CMS Migration",
            ),
            "seo_improvement": (
                "SEO Audit",
                "On-page Optimization",
                "Technical SEO",
                "Keyword Optimization",
            ),
            "performance_optimization": (
                "Performance Audit",
                "Image Optimization",
                "Caching & CDN",
                "Code Splitting & Lazy Loading",
            ),
            "accessibility_improvement": (
                "WCAG Compliance Audit",
                "Alt Text & ARIA Improvements",
                "Keyboard Navigation Fixes",
            ),
            "content_improvement": (
                "Content Strategy",
                "Service Page Copywriting",
                "SEO Blog Content",
            ),
            "brand_refresh": (
                "Brand Refresh",
                "Logo & Visual Identity",
                "Modern UI Design",
            ),
            "technical_modernization": (
                "Modernization Assessment",
                "Framework Migration",
                "CMS Migration",
                "Tech Stack Upgrade",
            ),
            "mobile_optimization": (
                "Responsive Design",
                "Mobile UX Audit",
                "Mobile Speed Optimization",
            ),
            "analytics_setup": (
                "Google Analytics Setup",
                "Conversion Tracking",
                "Google Tag Manager",
                "Analytics Dashboard Setup",
            ),
            "security_improvement": (
                "SSL/HTTPS Migration",
                "Security Audit",
                "Malware Cleanup & Hardening",
            ),
            "local_seo": (
                "Local SEO Audit",
                "Google Business Profile Optimization",
                "Local Citations",
                "Local Structured Data",
            ),
            "contact_funnel_improvement": (
                "Contact Page Design",
                "Contact Form Setup",
                "Call-to-Action Optimization",
                "Click-to-Call",
            ),
            "conversion_optimization": (
                "CRO Audit",
                "Landing Page Optimization",
                "A/B Testing",
                "Form UX Improvement",
            ),
            "hosting_upgrade": (
                "Managed Hosting Migration",
                "CDN Setup",
                "Server Optimization",
                "Uptime Monitoring",
            ),
            "ecommerce_optimization": (
                "E-commerce Audit",
                "Product Page Optimization",
                "Checkout Optimization",
                "Conversion Tracking",
            ),
            "maintenance_opportunity": (
                "Website Maintenance Plan",
                "Security Updates",
                "Backup & Monitoring",
                "Content Updates",
            ),
        }
    )

    category_impact: dict[str, str] = field(
        default_factory=lambda: {
            "website_redesign": "High",
            "seo_improvement": "High",
            "performance_optimization": "Medium",
            "accessibility_improvement": "Medium",
            "content_improvement": "Medium",
            "brand_refresh": "Medium",
            "technical_modernization": "High",
            "mobile_optimization": "Medium",
            "analytics_setup": "Medium",
            "security_improvement": "Very High",
            "local_seo": "High",
            "contact_funnel_improvement": "High",
            "conversion_optimization": "High",
            "hosting_upgrade": "Medium",
            "ecommerce_optimization": "Very High",
            "maintenance_opportunity": "Medium",
        }
    )

    category_effort: dict[str, str] = field(
        default_factory=lambda: {
            "website_redesign": "Hard",
            "seo_improvement": "Medium",
            "performance_optimization": "Medium",
            "accessibility_improvement": "Medium",
            "content_improvement": "Medium",
            "brand_refresh": "Medium",
            "technical_modernization": "Hard",
            "mobile_optimization": "Easy",
            "analytics_setup": "Easy",
            "security_improvement": "Medium",
            "local_seo": "Easy",
            "contact_funnel_improvement": "Easy",
            "conversion_optimization": "Medium",
            "hosting_upgrade": "Easy",
            "ecommerce_optimization": "Medium",
            "maintenance_opportunity": "Easy",
        }
    )

    # Derived constants (not tunable via constructor).
    def label_for(self, category: str) -> str:
        return CATEGORY_LABELS.get(category, category.replace("_", " ").title())

    def services_for(self, category: str) -> tuple[str, ...]:
        return self.service_mapping.get(category, ())

    def impact_for(self, category: str) -> str:
        return self.category_impact.get(category, "Medium")

    def effort_for(self, category: str) -> str:
        return self.category_effort.get(category, "Medium")


def default_config() -> OpportunityConfig:
    return OpportunityConfig()
