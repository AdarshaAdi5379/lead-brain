from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

# Website enrichment tunables (mirrors ScoringConfig / VisualConfig: engine
# code carries no magic numbers, settings are overridable via env).


@dataclass(frozen=True)
class EnrichmentConfig:
    enabled: bool = True
    # Free anonymous web search (DuckDuckGo HTML) as a candidate source.
    search_enabled: bool = True
    # Minimum deterministic score (0-1) before a website is stored.
    accept_threshold: float = 0.75
    # Confidence-band boundaries (inclusive minimums).
    high_min: float = 0.75
    medium_min: float = 0.60
    # Politeness / safety bounds for candidate page fetches.
    fetch_timeout_s: float = 10.0
    max_fetch_bytes: int = 300_000
    # At most this many candidates are fetched/verified per lead.
    max_candidates: int = 3
    # Maximum organic results taken from the search page.
    max_search_results: int = 5
    # Lookups are cached locally for this many days per business.
    cache_ttl_days: int = 30
    user_agent: str = "lead-brain/1.0 (local lead finder; enrichment)"
    search_url: str = "https://html.duckduckgo.com/html/"
    search_timeout_s: float = 12.0


def from_settings(settings: object, defaults: Optional[EnrichmentConfig] = None) -> EnrichmentConfig:
    """Build an EnrichmentConfig from the module-level settings object.

    Uses the defaults for anything the settings module does not define, so
    tests and non-pipeline callers can construct a config with plain values.
    """
    base = defaults or EnrichmentConfig()

    def _bool(name: str, fallback: bool) -> bool:
        value = getattr(settings, name, None)
        if isinstance(value, bool):
            return value
        if value is None:
            return fallback
        return str(value).strip().lower() in {"1", "true", "yes", "on"}

    def _float(name: str, fallback: float) -> float:
        value = getattr(settings, name, None)
        return float(value) if value is not None else fallback

    def _int(name: str, fallback: int) -> int:
        value = getattr(settings, name, fallback)
        return int(value) if value is not None else fallback

    return EnrichmentConfig(
        enabled=_bool("ENRICHMENT_ENABLED", base.enabled),
        search_enabled=_bool("ENRICHMENT_SEARCH_ENABLED", base.search_enabled),
        accept_threshold=_float("ENRICHMENT_ACCEPT_THRESHOLD", base.accept_threshold),
        high_min=_float("ENRICHMENT_CONFIDENCE_HIGH_MIN", base.high_min),
        medium_min=_float("ENRICHMENT_CONFIDENCE_MEDIUM_MIN", base.medium_min),
        fetch_timeout_s=_float("ENRICHMENT_FETCH_TIMEOUT_S", base.fetch_timeout_s),
        max_fetch_bytes=_int("ENRICHMENT_MAX_FETCH_BYTES", base.max_fetch_bytes),
        max_candidates=_int("ENRICHMENT_MAX_CANDIDATES", base.max_candidates),
        max_search_results=_int("ENRICHMENT_MAX_SEARCH_RESULTS", base.max_search_results),
        cache_ttl_days=_int("ENRICHMENT_CACHE_TTL_DAYS", base.cache_ttl_days),
        user_agent=getattr(settings, "ENRICHMENT_USER_AGENT", None) or base.user_agent,
        search_url=getattr(settings, "ENRICHMENT_SEARCH_URL", None) or base.search_url,
        search_timeout_s=_float("ENRICHMENT_SEARCH_TIMEOUT_S", base.search_timeout_s),
    )


def confidence_label(score: Optional[float], config: EnrichmentConfig) -> str:
    """Map a 0-1 confidence score to a human label (high/medium/low)."""
    if score is None:
        return "low"
    if score >= config.high_min:
        return "high"
    if score >= config.medium_min:
        return "medium"
    return "low"