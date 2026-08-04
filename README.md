# Second Brain Lead Finder (v1)

Manual CSV → scrape (Playwright) → visual audit → LLM extract → score → SQLite → CSV exports → Streamlit dashboard.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m playwright install --with-deps chromium
```

Create a `.env` file:

```bash
OPENAI_API_KEY=...

# Optional (only required if you use --max-cost-usd)
OPENAI_INPUT_COST_PER_1K=0.0
OPENAI_OUTPUT_COST_PER_1K=0.0
```

Seed CSV format:
- `business_name,category,url,city,state`
- See `business_urls.sample.csv`.

## Multi-page website crawl

When auditing a site, the pipeline now crawls the homepage plus its top ranked
internal pages (about/services/contact/…), trims each page, and sends one merged,
labelled document to the LLM instead of homepage-only text. Page selection is
deterministic (rules-based, no API keys). Pages are cached by content hash on
disk in `data/crawl_cache/`, so unchanged pages are reused across runs.

```bash
# Default: crawl (homepage + up to 4 ranked internal pages, depth 1)
python main.py --input business_urls.csv --limit 200

# Restore v1 homepage-only behavior
python main.py --input business_urls.csv --no-crawl --limit 200

# Empty the crawl cache
python main.py --input business_urls.csv --clear-crawl-cache --limit 200
```

Tunables (env / via `src/settings.py`): `MAX_CRAWL_PAGES` (5),
`MAX_CRAWL_DEPTH` (1), `MAX_PAGE_CHARACTERS` (2000),
`CRAWL_CACHE_DIR`, `CRAWL_CACHE_FILE`.

Smoke-test the crawler against any site:

```bash
python -m src.scraping.focused_crawler https://example.com --pages 5
```

## Local visual audit

After the multi-page crawl, the pipeline runs an offline, **local** visual quality
audit before LLM extraction: it takes bounded desktop + mobile screenshots
(Playwright, or reuses cached HTML) and runs deterministic, model-free quality
heuristics over them, then feeds the result to the LLM only as neutral context
text. No paid vision API is required. An optional multimodal summary is gated
behind `VISUAL_LLM_ENABLED` and degrades gracefully when an OpenAI key is absent.

Signals (additive, scored 0–100 with bands Excellent ≥85 / Good ≥70 / Fair ≥50 /
Poor ≥30): modern/outdated design, clutter, weak visual hierarchy, weak mobile
layout, weak/strong call-to-action, strong branding, responsive, low contrast.

```bash
# On by default whenever screenshots can be captured; disable with:
VISUAL_ENABLED=0 python main.py --input business_urls.csv --limit 200
```

Tunables (env / via `src/settings.py`): `VISUAL_ENABLED` (default true),
`VISUAL_VIEWPORT_DESKTOP` (`1365x900`), `VISUAL_VIEWPORT_MOBILE` (`390x844`),
`VISUAL_FULLPAGE_MAX_HEIGHT` (12000), `VISUAL_LLM_ENABLED` (default false),
`VISUAL_LLM_MODEL` / `OPENAI_VISION_MODEL` (`gpt-4o-mini`), `VISUAL_SCREENSHOT_DIR`
(`data/screenshots`, gitignored). Per-lead capture caps: `max_screenshots=5`,
`max_internal_pages=3`.

Inspect screenshots in the Lead detail view, or filter leads by **Visual health**,
**min visual score**, and per-signal flags (weak mobile, clutter, weak CTA, strong
branding) in the dashboard sidebar.

## Local semantic search (AI Search)

After each run, the pipeline **incrementally indexes** every lead's collected
intelligence (business info, technologies, SEO, visual, opportunities, scoring)
into `lead_embeddings` as one semantic document per lead — fully local and
offline, no API key required. Unchanged leads are skipped via content hashing;
`--no-index` skips indexing, `--rebuild-index` drops and rebuilds the whole
index.

```bash
# Search the index directly (acceptance check: "restaurants with poor SEO"):
python -c "
from pathlib import Path
from src.search.search_service import SearchService
from src.search.query import SearchQuery
svc = SearchService(Path('data/leads.sqlite'))
for r in svc.search(SearchQuery(text='restaurants with poor SEO', top_k=10)):
    print(r.business_name, r.lead_score, r.seo_score, r.priority)
"
```

Three search modes (`hybrid` default / `semantic` / `keyword`), combined with
whitelisted filters (category, city, state, country, platform, priority,
technologies, website present, SEO/lead/visual/opportunity score ranges), a
"Find similar businesses" (top-10, excludes self), and a neutral per-lead **AI
context** block for a future chat/outreach assistant. Use it from the
dashboard's **AI Search** page.

Default engine: deterministic `hash-ngram-512` embedder + SQLite brute-force
cosine store (numpy-accelerated) — no dependencies. Optional upgrade to
sentence-transformers embeddings and a ChromaDB accelerator:

```bash
pip install -r requirements-search.txt
# .env: SEARCH_EMBEDDER=sentence  SEARCH_VECTOR_STORE=chroma   (or rely on "auto")
```

Tunables (env / `src/settings.py`): `SEARCH_ENABLED` (default true),
`SEARCH_EMBEDDER` (`auto|hash|sentence`), `SEARCH_EMBEDDING_MODEL`
(`all-MiniLM-L6-v2`, fallback `bge-small-en-v1.5`), `SEARCH_EMBEDDING_DEVICE`
(`cpu`), `SEARCH_HASH_DIMENSIONS` (512), `SEARCH_VECTOR_STORE`
(`auto|sqlite|chroma`), `SEARCH_CHROMA_DIR` (`data/chroma`, gitignored),
`SEARCH_BATCH_SIZE` (32), `SEARCH_TOP_K` (20), `SEARCH_HYBRID_WEIGHT` (0.7),
`SEARCH_RANK_WEIGHT_SIMILARITY/LEAD/OPPORTUNITY/RECENCY` (0.5/0.25/0.15/0.10),
`SEARCH_MAX_QUERY_CHARS` (500). Switching the embedder invalidates the cache and
re-indexes automatically.

## Run pipeline

```bash
python -m src.storage.init_db
python main.py --input business_urls.csv --limit 200 --min-score-export 30
```

Re-run failed leads already in the DB:

```bash
python main.py --input business_urls.csv --only-failed --limit 200
```

Cost stop (optional):

```bash
export OPENAI_INPUT_COST_PER_1K=0.0
export OPENAI_OUTPUT_COST_PER_1K=0.0
python main.py --input business_urls.csv --max-cost-usd 5
```

## Dashboard

```bash
streamlit run dashboard.py
```

## Discovery mode (OpenStreetMap — free, no API key)

Discover leads automatically without a seed CSV. The default provider uses
OpenStreetMap (Nominatim for geocoding + Overpass API for POIs), which is free
and needs no key. Responses are cached on disk in `data/cache/`.

```bash
# Inline: single query (default provider = osm, free)
python main.py --discover --category plumber --location "Austin, TX" --limit 50

# Batch: CSV of queries (columns: category, location)
python main.py --discover --discover-queries queries.csv --limit 200

# Explicit provider + clear the discovery cache
python main.py --discover --provider osm --category salon --location "Dallas, TX"
python main.py --clear-cache
```

Supported categories include plumber, electrician, hvac, roofer, painter,
landscaper, handyman, locksmith, tree service, restaurant, cafe, bakery, pizza,
salon, barber, beauty, gym, car wash, auto repair, dry cleaner, laundry,
dentist, pharmacy, contractor, flooring, + more (mapped to OSM tags in
`CATEGORY_TAGS`); unmapped categories fall back to a name-keyword search.

`google` is still supported but deprecated and requires a paid
`GOOGLE_MAPS_API_KEY` in `.env`:
`python main.py --discover --provider google --category plumber --location "Austin, TX" --limit 50`

## Tests

```bash
python -m unittest discover -s tests
```
