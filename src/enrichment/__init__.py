from __future__ import annotations

from src.enrichment.base import (
    EMAIL_DOMAIN,
    FAILED,
    FOUND,
    LOW_CONFIDENCE,
    NOT_FOUND,
    NOT_NEEDED,
    OSM_TAGS,
    STATUSES,
    WEB_SEARCH,
    EnrichmentCandidate,
    EnrichmentResult,
    LeadContext,
)
from src.enrichment.cache import CacheEntry, EnrichmentCache, query_key
from src.enrichment.config import EnrichmentConfig, confidence_label, from_settings
from src.enrichment.match import (
    brand_component,
    email_domain_candidate,
    email_domain_component,
    location_component,
    phone_component,
    score_candidate,
)
from src.enrichment.normalizer import clean_candidate_url, rejected_host
from src.enrichment.report import EnrichmentReport
from src.enrichment.search import SearchClient, build_search_query, search_web
from src.enrichment.service import run_enrichment
from src.enrichment.verifier import PageVerification, fetch_page, verify_candidate

__all__ = [
    "EMAIL_DOMAIN",
    "FAILED",
    "FOUND",
    "LOW_CONFIDENCE",
    "NOT_FOUND",
    "NOT_NEEDED",
    "OSM_TAGS",
    "STATUSES",
    "WEB_SEARCH",
    "CacheEntry",
    "EnrichmentCache",
    "EnrichmentCandidate",
    "EnrichmentConfig",
    "EnrichmentReport",
    "EnrichmentResult",
    "LeadContext",
    "PageVerification",
    "SearchClient",
    "brand_component",
    "build_search_query",
    "clean_candidate_url",
    "confidence_label",
    "email_domain_candidate",
    "email_domain_component",
    "fetch_page",
    "from_settings",
    "location_component",
    "phone_component",
    "query_key",
    "rejected_host",
    "run_enrichment",
    "score_candidate",
    "search_web",
    "verify_candidate",
]