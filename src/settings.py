from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
DB_PATH = DATA_DIR / "leads.sqlite"

# Google Places API (Phase 8 — Lead Discovery) [deprecated provider]
GOOGLE_MAPS_API_KEY: Optional[str] = os.environ.get("GOOGLE_MAPS_API_KEY", "").strip() or None
PLACES_TEXT_SEARCH_RADIUS: int = int(os.environ.get("GOOGLE_PLACES_TEXT_SEARCH_RADIUS", "50000"))
PLACES_LANGUAGE: str = os.environ.get("GOOGLE_PLACES_LANGUAGE", "en")

# OpenStreetMap-based discovery (Phase 9 — default provider, no API keys)
OSM_USER_AGENT: str = os.environ.get(
    "OSM_USER_AGENT", "lead-brain/1.0 (local lead finder; contact: leadfinder@localhost)"
)
OVERPASS_API_URL: str = os.environ.get("OVERPASS_API_URL", "https://overpass-api.de/api/interpreter")
NOMINATIM_URL: str = os.environ.get("NOMINATIM_URL", "https://nominatim.openstreetmap.org/search")
NOMINATIM_REVERSE_URL: str = os.environ.get(
    "NOMINATIM_REVERSE_URL", "https://nominatim.openstreetmap.org/reverse"
)

# Fallback radius (metres) when a location geocodes to a point but not a bbox.
OVERPASS_RADIUS: int = int(os.environ.get("OVERPASS_RADIUS", "10000"))

# Politeness / resilience tunables (free public endpoints throttle heavily).
OVERPASS_DELAY_SECONDS: float = float(os.environ.get("OVERPASS_DELAY_SECONDS", "1.0"))
OVERPASS_MAX_RETRIES: int = int(os.environ.get("OVERPASS_MAX_RETRIES", "3"))
OVERPASS_RETRY_BACKOFF_SECONDS: float = float(
    os.environ.get("OVERPASS_RETRY_BACKOFF_SECONDS", "2.0")
)
NOMINATIM_DELAY_SECONDS: float = float(os.environ.get("NOMINATIM_DELAY_SECONDS", "1.0"))
NOMINATIM_MAX_RETRIES: int = int(os.environ.get("NOMINATIM_MAX_RETRIES", "3"))
HTTP_TIMEOUT_SECONDS: float = float(os.environ.get("HTTP_TIMEOUT_SECONDS", "30"))

# Local disk cache for geocoding + discovery responses (data/ is gitignored).
DISCOVERY_CACHE_DIR: Path = PROJECT_ROOT / os.environ.get("DISCOVERY_CACHE_DIR", "data/cache")
DISCOVERY_GEO_CACHE_TTL_HOURS: float = float(
    os.environ.get("DISCOVERY_GEO_CACHE_TTL_HOURS", "24")
)
DISCOVERY_POI_CACHE_TTL_HOURS: float = float(
    os.environ.get("DISCOVERY_POI_CACHE_TTL_HOURS", str(24 * 7))
)

# Focused multi-page website crawl (Phase 10). All overridable via env.
# Maximum pages visited per site, including the homepage.
MAX_CRAWL_PAGES: int = int(os.environ.get("MAX_CRAWL_PAGES", "5"))
# Crawler never recurses; depth is kept for clarity + future guard rails.
MAX_CRAWL_DEPTH: int = int(os.environ.get("MAX_CRAWL_DEPTH", "1"))
# Per-page character budget sent to the LLM (paragraph-boundary truncation).
MAX_PAGE_CHARACTERS: int = int(os.environ.get("MAX_PAGE_CHARACTERS", "2000"))
# Persisted page cache (per-page content hash + cleaned text) so unchanged
# pages are skipped on later runs without re-fetching or re-sending to the LLM.
CRAWL_CACHE_DIR: Path = PROJECT_ROOT / os.environ.get("CRAWL_CACHE_DIR", "data/crawl_cache")
CRAWL_CACHE_FILE: str = os.environ.get("CRAWL_CACHE_FILE", "pages.json")
