"""Synthetic fixtures for the deterministic opportunity engine tests (no network)."""

from src.scoring.base import ScoringInputs
from tests.scoring_fixtures import strong_site_inputs, weak_site_inputs  # noqa: F401


def legacy_platform_inputs() -> ScoringInputs:
    """A Wix site on a legacy platform with weak trust signals."""
    return ScoringInputs(
        extracted={
            "business_name": "Old Style Co",
            "phone": "512-555-0400",
            "email": "old@example.com",
            "platform": "wix",
            "complexity": "basic",
            "load_speed": "slow",
            "extraction_success": True,
        },
        business_name="Old Style Co",
        category="dentist",
        city="Austin",
        state="TX",
        website_url="http://oldstyle.example.com",
        fetch_ok=True,
        detections=[
            {"technology_name": "Wix", "category": "cms", "confidence": 90},
            {"technology_name": "jQuery", "category": "libraries", "confidence": 80},
        ],
        crawl={
            "ok": True,
            "merged_text": "word " * 800,
            "contact_clues": [],
            "pages": [
                {"url": "http://oldstyle.example.com/", "label": "HOME", "text": "word " * 200},
            ],
        },
        seo_audit={
            "site_score": 30,
            "overall_health": "Poor",
            "total_pages_audited": 1,
            "html_pages": 1,
            "pages_with_title": 0,
            "pages_with_meta_description": 0,
            "pages_with_json_ld": 0,
            "pages_with_duplicate_titles": 1,
            "pages_with_duplicate_descriptions": 0,
            "pages_with_thin_content": 1,
            "pages_with_images_missing_alt": 2,
            "pages_with_noindex": 0,
            "pages_with_mixed_content": 1,
            "robots_txt_detected": 0,
            "sitemap_detected": 0,
            "pages": [
                {
                    "page_type": "home",
                    "word_count": 200,
                    "html_available": 1,
                    "viewport_present": 0,
                    "images_missing_alt_count": 2,
                    "og_title_present": 0,
                    "twitter_card_present": 0,
                }
            ],
        },
    )


def ecommerce_inputs() -> ScoringInputs:
    """A Shopify store with analytics but weak conversion signals."""
    return ScoringInputs(
        extracted={
            "business_name": "Modern Goods",
            "phone": "512-555-0500",
            "email": None,
            "platform": "shopify",
            "complexity": "medium",
            "load_speed": "slow",
            "extraction_success": True,
        },
        business_name="Modern Goods",
        category="retail",
        city="Austin",
        state="TX",
        website_url="https://moderngoods.example.com",
        fetch_ok=True,
        detections=[
            {"technology_name": "Shopify", "category": "cms", "confidence": 90},
            {"technology_name": "Google Analytics", "category": "analytics", "confidence": 85},
        ],
        crawl={
            "ok": True,
            "merged_text": "word " * 2000,
            "contact_clues": [],
            "pages": [
                {"url": "https://moderngoods.example.com/", "label": "HOME", "text": "word " * 400},
            ],
        },
        seo_audit={
            "site_score": 70,
            "overall_health": "Good",
            "total_pages_audited": 1,
            "html_pages": 1,
            "pages_with_title": 1,
            "pages_with_meta_description": 1,
            "pages_with_json_ld": 0,
            "pages_with_duplicate_titles": 0,
            "pages_with_duplicate_descriptions": 0,
            "pages_with_thin_content": 0,
            "pages_with_images_missing_alt": 0,
            "pages_with_noindex": 0,
            "pages_with_mixed_content": 0,
            "robots_txt_detected": 1,
            "sitemap_detected": 1,
            "pages": [
                {"page_type": "home", "word_count": 400, "html_available": 1, "viewport_present": 1},
            ],
        },
    )
