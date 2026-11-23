from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
DB_PATH = DATA_DIR / "leads.sqlite"

# LLM provider (Phase 16 — OpenRouter). Active default provider for all LLM
# calls (extraction + optional visual summarizer). OpenAI-compatible base URL;
# the free router (`openrouter/free`) is the default model. Legacy OPENAI_*
# variables remain honored only as backward-compatible overrides.
OPENROUTER_API_KEY: Optional[str] = os.environ.get("OPENROUTER_API_KEY", "").strip() or None
OPENROUTER_BASE_URL: str = os.environ.get(
    "OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"
).rstrip("/")
OPENROUTER_MODEL: str = os.environ.get("OPENROUTER_MODEL", "").strip() or "openrouter/free"
# Optional attribution headers sent to OpenRouter only when set.
OPENROUTER_HTTP_REFERER: str = os.environ.get("OPENROUTER_HTTP_REFERER", "").strip()
OPENROUTER_X_TITLE: str = os.environ.get("OPENROUTER_X_TITLE", "").strip()

# Local Excel CRM workbook (Phase 18). Editable CRM layer on top of SQLite;
# auto-filled from lead data, manual CRM fields win on merge.
CRM_WORKBOOK_PATH: Path = DATA_DIR / "lead_crm.xlsx"

# OpenStreetMap-based discovery (Phase 9 — default provider, no API keys)
OSM_USER_AGENT: str = os.environ.get(
    "OSM_USER_AGENT", "lead-brain/1.0 (local lead finder; contact: leadfinder@localhost)"
)
OVERPASS_API_URL: str = os.environ.get("OVERPASS_API_URL", "https://overpass-api.de/api/interpreter")
OVERPASS_FALLBACK_URLS: list[str] = [
    url.strip()
    for url in os.environ.get(
        "OVERPASS_FALLBACK_URLS",
        "https://lz4.overpass-api.de/api/interpreter,"
        "https://overpass.kumi.systems/api/interpreter,"
        "https://overpass.private.coffee/api/interpreter",
    ).split(",")
    if url.strip()
]

# Website enrichment (Phase 19). Free, local-first website recovery for leads
# without a website URL: OSM tags + email-domain candidates + an anonymous
# free web search (DuckDuckGo HTML), all deterministically verified. Skipped
# automatically under --no-crawl (offline runs stay offline).
ENRICHMENT_ENABLED: bool = os.environ.get("ENRICHMENT_ENABLED", "1").strip().lower() in {"1", "true", "yes", "on"}
ENRICHMENT_SEARCH_ENABLED: bool = os.environ.get("ENRICHMENT_SEARCH_ENABLED", "1").strip().lower() in {"1", "true", "yes", "on"}
ENRICHMENT_ACCEPT_THRESHOLD: float = float(os.environ.get("ENRICHMENT_ACCEPT_THRESHOLD", "0.75"))
ENRICHMENT_CONFIDENCE_HIGH_MIN: float = float(os.environ.get("ENRICHMENT_CONFIDENCE_HIGH_MIN", "0.75"))
ENRICHMENT_CONFIDENCE_MEDIUM_MIN: float = float(os.environ.get("ENRICHMENT_CONFIDENCE_MEDIUM_MIN", "0.60"))
ENRICHMENT_MAX_CANDIDATES: int = int(os.environ.get("ENRICHMENT_MAX_CANDIDATES", "3"))
ENRICHMENT_MAX_SEARCH_RESULTS: int = int(os.environ.get("ENRICHMENT_MAX_SEARCH_RESULTS", "5"))
ENRICHMENT_FETCH_TIMEOUT_S: float = float(os.environ.get("ENRICHMENT_FETCH_TIMEOUT_S", "10"))
ENRICHMENT_MAX_FETCH_BYTES: int = int(os.environ.get("ENRICHMENT_MAX_FETCH_BYTES", "300000"))
ENRICHMENT_CACHE_TTL_DAYS: int = int(os.environ.get("ENRICHMENT_CACHE_TTL_DAYS", "30"))
ENRICHMENT_USER_AGENT: str = os.environ.get("ENRICHMENT_USER_AGENT", "") or OSM_USER_AGENT
ENRICHMENT_SEARCH_URL: str = os.environ.get("ENRICHMENT_SEARCH_URL", "https://html.duckduckgo.com/html/")
ENRICHMENT_SEARCH_TIMEOUT_S: float = float(os.environ.get("ENRICHMENT_SEARCH_TIMEOUT_S", "12"))

# Google Places API (Phase 8 — Lead Discovery) [deprecated provider]
GOOGLE_MAPS_API_KEY: Optional[str] = os.environ.get("GOOGLE_MAPS_API_KEY", "").strip() or None
PLACES_TEXT_SEARCH_RADIUS: int = int(os.environ.get("GOOGLE_PLACES_TEXT_SEARCH_RADIUS", "50000"))
PLACES_LANGUAGE: str = os.environ.get("GOOGLE_PLACES_LANGUAGE", "en")
NOMINATIM_URL: str = os.environ.get("NOMINATIM_URL", "https://nominatim.openstreetmap.org/search")
NOMINATIM_REVERSE_URL: str = os.environ.get(
    "NOMINATIM_REVERSE_URL", "https://nominatim.openstreetmap.org/reverse"
)

# Fallback radius (metres) when a location geocodes to a point but not a bbox.
OVERPASS_RADIUS: int = int(os.environ.get("OVERPASS_RADIUS", "10000"))

# Politeness / resilience tunables (free public endpoints throttle heavily).
OVERPASS_DELAY_SECONDS: float = float(os.environ.get("OVERPASS_DELAY_SECONDS", "1.0"))
OVERPASS_MAX_RETRIES: int = int(os.environ.get("OVERPASS_MAX_RETRIES", "1"))
OVERPASS_RETRY_BACKOFF_SECONDS: float = float(
    os.environ.get("OVERPASS_RETRY_BACKOFF_SECONDS", "1.5")
)
NOMINATIM_DELAY_SECONDS: float = float(os.environ.get("NOMINATIM_DELAY_SECONDS", "1.0"))
NOMINATIM_MAX_RETRIES: int = int(os.environ.get("NOMINATIM_MAX_RETRIES", "2"))
HTTP_TIMEOUT_SECONDS: float = float(os.environ.get("HTTP_TIMEOUT_SECONDS", "15"))

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
VISUAL_LLM_MODEL: str = os.environ.get("OPENAI_VISION_MODEL", "").strip() or "openrouter/free"

# Local semantic search + AI knowledge base (Phase 14). Fully local, offline,
# no cloud and no paid APIs. Default engine is dependency-free: a deterministic
# hashing-n-gram embedder + SQLite vector store. When sentence-transformers
# and/or chromadb are installed they are used automatically (SEARCH_EMBEDDER /
# SEARCH_VECTOR_STORE = "auto").
# Master switch: when off, the pipeline never indexes and search is unavailable.
SEARCH_ENABLED: bool = os.environ.get("SEARCH_ENABLED", "1").strip().lower() in {"1", "true", "yes", "on"}
# Embedder backend: "auto" (sentence-transformers if importable, else hash),
# "hash" (pure stdlib, always works), "sentence" (requires the optional package).
SEARCH_EMBEDDER: str = os.environ.get("SEARCH_EMBEDDER", "auto").strip().lower()
SEARCH_EMBEDDING_MODEL: str = os.environ.get("SEARCH_EMBEDDING_MODEL", "all-MiniLM-L6-v2")
SEARCH_EMBEDDING_MODEL_FALLBACK: str = os.environ.get(
    "SEARCH_EMBEDDING_MODEL_FALLBACK", "bge-small-en-v1.5"
)
SEARCH_EMBEDDING_DEVICE: str = os.environ.get("SEARCH_EMBEDDING_DEVICE", "cpu")
# Feature-space size for the deterministic hashing embedder.
SEARCH_HASH_DIMENSIONS: int = int(os.environ.get("SEARCH_HASH_DIMENSIONS", "512"))
# Vector store backend: "auto" (chromadb if importable, else sqlite),
# "sqlite" (pure stdlib, default), "chroma" (requires the optional package).
SEARCH_VECTOR_STORE: str = os.environ.get("SEARCH_VECTOR_STORE", "auto").strip().lower()
SEARCH_CHROMA_DIR: Path = PROJECT_ROOT / os.environ.get("SEARCH_CHROMA_DIR", "data/chroma")
# Batch size for embedding generation (both backends).
SEARCH_BATCH_SIZE: int = int(os.environ.get("SEARCH_BATCH_SIZE", "32"))
# Default number of results per search / similarity call.
SEARCH_TOP_K: int = int(os.environ.get("SEARCH_TOP_K", "20"))
# Share of semantic (vector) similarity in hybrid search scores (0-1); the
# remainder goes to keyword overlap.
SEARCH_HYBRID_WEIGHT: float = float(os.environ.get("SEARCH_HYBRID_WEIGHT", "0.7"))
# Deterministic final-ranking weights (must sum to 1): similarity, lead score,
# opportunity score, recency.
SEARCH_RANK_WEIGHT_SIMILARITY: float = float(os.environ.get("SEARCH_RANK_WEIGHT_SIMILARITY", "0.5"))
SEARCH_RANK_WEIGHT_LEAD: float = float(os.environ.get("SEARCH_RANK_WEIGHT_LEAD", "0.25"))
SEARCH_RANK_WEIGHT_OPPORTUNITY: float = float(os.environ.get("SEARCH_RANK_WEIGHT_OPPORTUNITY", "0.15"))
SEARCH_RANK_WEIGHT_RECENCY: float = float(os.environ.get("SEARCH_RANK_WEIGHT_RECENCY", "0.10"))
# Hard cap on raw user-query length (safety).
SEARCH_MAX_QUERY_CHARS: int = int(os.environ.get("SEARCH_MAX_QUERY_CHARS", "500"))

# Grounded AI chat assistant over the lead database (Phase 15). Fully local:
# retrieval always works; synthesis only when a local LLM backend is available.
# Master switch: when off, the chat page is unavailable.
CHAT_ENABLED: bool = os.environ.get("CHAT_ENABLED", "1").strip().lower() in {"1", "true", "yes", "on"}
# Synthesis backend: "auto" (probe local Ollama then local OpenAI-compatible
# server), "ollama", "openai" (OpenAI-compatible /v1/chat/completions), "none"
# (retrieval summary mode only, no synthesis).
CHAT_LLM_BACKEND: str = os.environ.get("CHAT_LLM_BACKEND", "auto").strip().lower()
CHAT_OLLAMA_BASE_URL: str = os.environ.get("CHAT_OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
CHAT_OLLAMA_MODEL: str = os.environ.get("CHAT_OLLAMA_MODEL", "llama3.2")
# OpenAI-compatible endpoint (covers llama.cpp server, LM Studio, ...). The API
# key is optional and defaults to empty (no Authorization header).
CHAT_OPENAI_COMPATIBLE_BASE_URL: str = os.environ.get(
    "CHAT_OPENAI_COMPATIBLE_BASE_URL", "http://localhost:1234/v1"
).rstrip("/")
CHAT_OPENAI_COMPATIBLE_MODEL: str = os.environ.get("CHAT_OPENAI_COMPATIBLE_MODEL", "local-model")
CHAT_OPENAI_COMPATIBLE_API_KEY: Optional[str] = os.environ.get(
    "CHAT_OPENAI_COMPATIBLE_API_KEY", ""
).strip() or None
# Timeout for a single synthesis call (seconds).
CHAT_LLM_TIMEOUT_S: int = int(os.environ.get("CHAT_LLM_TIMEOUT_S", "60"))
# Context budget for retrieval-based answers.
CHAT_MAX_CONTEXT_LEADS: int = int(os.environ.get("CHAT_MAX_CONTEXT_LEADS", "8"))
CHAT_MAX_CONTEXT_CHARS: int = int(os.environ.get("CHAT_MAX_CONTEXT_CHARS", "24000"))
# Conversation history kept per session (most recent turns).
CHAT_MAX_HISTORY: int = int(os.environ.get("CHAT_MAX_HISTORY", "10"))
# When on, chat sessions/messages persist in SQLite (chat_sessions/chat_messages).
CHAT_PERSIST_SESSIONS: bool = os.environ.get("CHAT_PERSIST_SESSIONS", "1").strip().lower() in {"1", "true", "yes", "on"}
# Default number of leads retrieved per question.
CHAT_TOP_K: int = int(os.environ.get("CHAT_TOP_K", "15"))
