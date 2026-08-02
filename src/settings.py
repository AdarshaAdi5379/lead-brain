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

# Website technology fingerprinting (Phase 11). Deterministic, offline engine.
# Minimum confidence for a technology to be reported at all.
FINGERPRINT_MIN_CONFIDENCE: int = int(os.environ.get("FINGERPRINT_MIN_CONFIDENCE", "25"))
# Minimum confidence for a high-confidence fingerprint to override the LLM's
# guessed platform (only for platform-mapped technologies).
FINGERPRINT_MIN_OVERRIDE_CONFIDENCE: int = int(
    os.environ.get("FINGERPRINT_MIN_OVERRIDE_CONFIDENCE", "60")
)

# Deterministic local SEO audit (Phase 12). No paid APIs, no cloud, no LLM.
# Max HTML characters retained per page for the audit (bounds memory + disk).
SEO_PAGE_HTML_MAX_CHARS: int = int(os.environ.get("SEO_PAGE_HTML_MAX_CHARS", "150000"))
# When enabled, the audit probes same-origin /robots.txt and /sitemap.xml once
# per site (bounded). Disabled by default: the audit otherwise works purely
# from already-crawled HTML, with no extra network requests.
SEO_PROBE_ROBOTS: bool = os.environ.get("SEO_PROBE_ROBOTS", "").strip().lower() in {"1", "true", "yes", "on"}
# Weight of the site SEO score when blending into the lead score.
SEO_BLEND_WEIGHT: float = float(os.environ.get("SEO_BLEND_WEIGHT", "0.15"))

# Local visual website audit (Phase 13). Screenshots + deterministic
# computer-vision-lite heuristics; optional multimodal LLM summarizer.
# Master switch: when off, the visual stage is skipped entirely.
VISUAL_ENABLED: bool = os.environ.get("VISUAL_ENABLED", "1").strip().lower() in {"1", "true", "yes", "on"}
# When set, existing screenshots are re-captured instead of reused.
VISUAL_RECAPTURE: bool = os.environ.get("VISUAL_RECAPTURE", "").strip().lower() in {"1", "true", "yes", "on"}
# Capture viewports (width x height) for the desktop and mobile variants.
VISUAL_VIEWPORT_DESKTOP: str = os.environ.get("VISUAL_VIEWPORT_DESKTOP", "1365x900")
VISUAL_VIEWPORT_MOBILE: str = os.environ.get("VISUAL_VIEWPORT_MOBILE", "390x844")
# Full-page screenshots taller than this (px) are downgraded to viewport-only.
VISUAL_FULLPAGE_MAX_HEIGHT: int = int(os.environ.get("VISUAL_FULLPAGE_MAX_HEIGHT", "12000"))
# Screenshot directory (data/ is gitignored; paths are hash-based).
VISUAL_SCREENSHOT_DIR: Path = PROJECT_ROOT / os.environ.get("VISUAL_SCREENSHOT_DIR", "data/screenshots")
# Optional multimodal summarizer (gated: off by default, no API key needed).
VISUAL_LLM_ENABLED: bool = os.environ.get("VISUAL_LLM_ENABLED", "").strip().lower() in {"1", "true", "yes", "on"}
VISUAL_LLM_MODEL: str = os.environ.get("OPENAI_VISION_MODEL", "gpt-4o-mini")
