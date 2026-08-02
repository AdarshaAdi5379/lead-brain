from __future__ import annotations

from typing import Callable, Optional

from src.opportunities.base import Opportunity
from src.opportunities.config import OpportunityConfig
from src.opportunities.detectors import (
    detect_accessibility_improvement,
    detect_analytics_setup,
    detect_brand_refresh,
    detect_contact_funnel_improvement,
    detect_content_improvement,
    detect_conversion_optimization,
    detect_ecommerce_optimization,
    detect_hosting_upgrade,
    detect_local_seo,
    detect_maintenance_opportunity,
    detect_mobile_optimization,
    detect_performance_optimization,
    detect_security_improvement,
    detect_seo_improvement,
    detect_technical_modernization,
    detect_website_redesign,
)
from src.scoring.base import LeadScore, ScoringInputs

Detector = Callable[
    [ScoringInputs, Optional[LeadScore], OpportunityConfig], Optional[Opportunity]
]

# Ordered registry of independent detectors. Every detector is run for every
# lead; new detectors are added here without modifying existing ones.
OPPORTUNITY_DETECTORS: tuple[tuple[str, Detector], ...] = (
    ("website_redesign", detect_website_redesign),
    ("seo_improvement", detect_seo_improvement),
    ("performance_optimization", detect_performance_optimization),
    ("accessibility_improvement", detect_accessibility_improvement),
    ("content_improvement", detect_content_improvement),
    ("brand_refresh", detect_brand_refresh),
    ("technical_modernization", detect_technical_modernization),
    ("mobile_optimization", detect_mobile_optimization),
    ("analytics_setup", detect_analytics_setup),
    ("security_improvement", detect_security_improvement),
    ("local_seo", detect_local_seo),
    ("contact_funnel_improvement", detect_contact_funnel_improvement),
    ("conversion_optimization", detect_conversion_optimization),
    ("hosting_upgrade", detect_hosting_upgrade),
    ("ecommerce_optimization", detect_ecommerce_optimization),
    ("maintenance_opportunity", detect_maintenance_opportunity),
)
