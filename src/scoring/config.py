from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ScoringConfig:
    """Every tunable number used by the scoring engine.

    Adjusting weights or point values here is the supported way to tune the
    model; the engine itself stays read-only over this config.
    """

    # Weighted aggregation: contactability matters heavily, SEO/content
    # strongly, trust/technical moderately, discovery modestly. Outreach
    # potential is derived from the other dimensions, so it only biases the
    # result instead of standing alone.
    weights: dict[str, float] = field(
        default_factory=lambda: {
            "discovery_quality": 0.10,
            "contactability": 0.25,
            "technical_health": 0.15,
            "seo_health": 0.15,
            "content_strength": 0.10,
            "trust_professionalism": 0.10,
            "outreach_potential": 0.15,
        }
    )

    # (minimum_score, label) bands, evaluated in order.
    priority_bands: tuple[tuple[int, str], ...] = ((75, "Hot"), (55, "Warm"), (30, "Cold"))

    # --- discovery_quality ---
    discovery_category_points: int = 20
    discovery_location_points: int = 20
    discovery_identity_points: int = 15
    discovery_source_points: int = 15
    discovery_website_points: int = 15
    discovery_address_points: int = 10
    discovery_contact_points: int = 5

    # --- contactability ---
    contact_email_points: int = 30
    contact_phone_points: int = 25
    contact_page_points: int = 15
    contact_website_points: int = 15
    contact_clues_points: int = 10
    contact_address_points: int = 10
    contact_social_points: int = 5

    # --- technical_health ---
    tech_fetch_ok_points: int = 25
    tech_platform_known_points: int = 10
    tech_modern_points: int = 15
    tech_legacy_points: int = 5
    tech_fast_points: int = 15
    tech_detections_points: int = 10
    tech_broken_penalty: int = 30

    # --- seo_health ---
    seo_unverifiable_score: int = 25
    seo_no_website_score: int = 0
    seo_sitemap_points: int = 10
    seo_robots_points: int = 5
    seo_duplicate_titles_penalty: int = 10
    seo_duplicate_descriptions_penalty: int = 5
    seo_missing_structured_data_penalty: int = 10
    seo_thin_content_penalty: int = 5
    seo_missing_alt_penalty: int = 5

    # --- content_strength ---
    content_homepage_words_target: int = 300
    content_homepage_points: int = 40
    content_services_points: int = 25
    content_about_points: int = 15
    content_multi_page_points: int = 10
    content_text_points: int = 10
    content_text_chars_target: int = 1000

    # --- trust_professionalism ---
    trust_https_points: int = 20
    trust_branding_points: int = 10
    trust_contact_visible_points: int = 15
    trust_modern_points: int = 10
    trust_social_meta_points: int = 15
    trust_live_content_points: int = 10
    trust_noindex_penalty: int = 20

    # --- outreach_potential (bias dimension, derived from the others) ---
    outreach_contactable_points: int = 30
    outreach_contactable_min: int = 50
    outreach_improvement_points: int = 30
    outreach_improvement_max: int = 50
    outreach_active_points: int = 20
    outreach_service_site_points: int = 20

    # Reason output limits.
    top_reasons_max: int = 5


def default_config() -> ScoringConfig:
    return ScoringConfig()
