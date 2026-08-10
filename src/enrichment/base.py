from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

# Website enrichment outcomes (stored in lead.enrichment_status).
NOT_NEEDED = "not_needed"
FOUND = "found"
NOT_FOUND = "not_found"
LOW_CONFIDENCE = "low_confidence"
FAILED = "failed"

STATUSES = (NOT_NEEDED, FOUND, NOT_FOUND, LOW_CONFIDENCE, FAILED)

# Where the verified website came from (lead.enrichment_source).
OSM_TAGS = "osm_tags"
EMAIL_DOMAIN = "email_domain"
WEB_SEARCH = "web_search"


@dataclass(frozen=True)
class LeadContext:
    """Lead facts the enrichment engine can match against candidate sites.

    Mirrors the seed fields so the engine stays decoupled from the pipeline's
    seed loader; every field is optional and nullable-safe.
    """

    business_name: Optional[str] = None
    category: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    postal_code: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    source: Optional[str] = None

    @classmethod
    def from_seed(cls, seed: object) -> "LeadContext":
        return cls(
            business_name=seed.business_name or None,
            category=seed.category or None,
            city=seed.city or None,
            state=seed.state or None,
            country=seed.country or None,
            phone=seed.phone or None,
            email=seed.email or None,
            address=seed.address or None,
            postal_code=seed.postal_code or None,
            latitude=seed.latitude,
            longitude=seed.longitude,
            source=seed.source or None,
        )


@dataclass(frozen=True)
class EnrichmentCandidate:
    """One candidate website URL plus the source it was discovered from."""

    url: str
    source: str


@dataclass(frozen=True)
class EnrichmentResult:
    """Outcome of the enrichment attempt for one lead."""

    status: str
    website_url: Optional[str] = None
    source: Optional[str] = None
    confidence: Optional[float] = None
    last_error: Optional[str] = None
    checked_at: str = ""