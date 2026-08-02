"""Synthetic fixtures for the deterministic scoring engine tests (no network)."""

from src.scoring.base import ScoringInputs


def strong_site_inputs() -> ScoringInputs:
    """A healthy, reachable, well-built business site."""
    return ScoringInputs(
        extracted={
            "business_name": "Acme Plumbing",
            "phone": "512-555-0100",
            "email": "acme@example.com",
            "platform": "custom_react",
            "complexity": "medium",
            "load_speed": "fast",
            "extraction_success": True,
        },
        business_name="Acme Plumbing",
        category="plumber",
        city="Austin",
        state="TX",
        address="100 Main St",
        source="osm",
        osm_id="12345",
        website_url="https://acme.example.com",
        fetch_ok=True,
        detections=[
            {"technology_name": "React", "category": "frontend", "confidence": 90},
            {"technology_name": "nginx", "category": "hosting", "confidence": 80},
        ],
        crawl={
            "ok": True,
            "merged_text": "word " * 5000,
            "contact_clues": ["acme@example.com", "512-555-0100"],
            "pages": [
                {"url": "https://acme.example.com/", "label": "HOME", "text": "word " * 500},
                {"url": "https://acme.example.com/services", "label": "SERVICES", "text": "word " * 300},
                {"url": "https://acme.example.com/about", "label": "ABOUT", "text": "word " * 300},
                {"url": "https://acme.example.com/contact", "label": "CONTACT", "text": "word " * 200},
            ],
        },
        seo_audit={
            "site_score": 92,
            "overall_health": "Excellent",
            "total_pages_audited": 4,
            "html_pages": 4,
            "pages_with_title": 4,
            "pages_with_meta_description": 4,
            "pages_with_json_ld": 3,
            "pages_with_duplicate_titles": 0,
            "pages_with_duplicate_descriptions": 0,
            "pages_with_thin_content": 0,
            "pages_with_images_missing_alt": 0,
            "pages_with_noindex": 0,
            "robots_txt_detected": 1,
            "sitemap_detected": 1,
            "pages": [{"page_type": "home", "word_count": 500}],
        },
    )


def weak_site_inputs() -> ScoringInputs:
    """A thin, unoptimized site with weak contact and trust signals."""
    return ScoringInputs(
        extracted={
            "business_name": "Weak Co",
            "phone": None,
            "email": None,
            "platform": "unknown",
            "complexity": "unknown",
            "load_speed": "unknown",
            "extraction_success": False,
        },
        business_name="Weak Co",
        category="plumber",
        city="Austin",
        state="TX",
        website_url="http://weak.example.com",
        fetch_ok=True,
        crawl={
            "ok": True,
            "merged_text": "tiny " * 20,
            "contact_clues": [],
            "pages": [{"url": "http://weak.example.com/", "label": "HOME", "text": "tiny " * 30}],
        },
        seo_audit={
            "site_score": 35,
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
            "pages_with_noindex": 1,
            "robots_txt_detected": 0,
            "sitemap_detected": 0,
            "pages": [{"page_type": "home", "word_count": 30}],
        },
    )


def no_website_inputs() -> ScoringInputs:
    """A real, contactable business with no website at all."""
    return ScoringInputs(
        extracted={
            "business_name": "Corner Plumbing",
            "phone": "512-555-0200",
            "email": "corner@example.com",
            "platform": "unknown",
            "complexity": "unknown",
            "load_speed": "unknown",
            "extraction_success": False,
        },
        business_name="Corner Plumbing",
        category="plumber",
        city="Austin",
        state="TX",
        address="200 Oak Ave",
        source="osm",
        osm_id="999",
        website_url=None,
        fetch_ok=False,
    )


def extraction_failed_inputs() -> ScoringInputs:
    """Website exists but could not be fetched (HTTP error)."""
    return ScoringInputs(
        extracted={
            "business_name": "Broken But Real",
            "phone": "512-555-0300",
            "email": "broken@example.com",
            "platform": "unknown",
            "complexity": "unknown",
            "load_speed": "unknown",
            "extraction_success": False,
            "last_error": "HTTP 500",
        },
        business_name="Broken But Real",
        category="electrician",
        city="Austin",
        state="TX",
        website_url="https://broken.example.com",
        fetch_ok=False,
        last_error="HTTP 500",
    )
