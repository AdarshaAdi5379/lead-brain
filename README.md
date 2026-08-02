# Second Brain Lead Finder (v1)

Manual CSV → scrape (Playwright) → LLM extract → score → SQLite → CSV exports → Streamlit dashboard.

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
