Session Notes — lead-brain
Last updated: 2026-05-19 (Asia/Kolkata)

Repo
- GitHub: `AdarshaAdi5379/lead-brain`
- Default branch: `main`

What’s implemented so far

Phase 0 — Repo/Env (completed)
- Dependencies: `requirements.txt`
- Docs: `README.md` + `business_urls.sample.csv`
- Optional `.env` loading (if `python-dotenv` installed): `main.py`, `dashboard.py`

Phase 1 — Storage (completed)
- SQLite DB path: `data/leads.sqlite` (`src/settings.py`)
- Schema + init:
  - `scraping_runs` table
  - `leads` table with:
    - `run_id` FK to `scraping_runs`
    - `last_error`
    - `website_url_normalized` unique index for dedupe
  - Code: `src/storage/db.py`, `src/storage/init_db.py`
- URL normalization (for dedupe): `src/storage/normalization.py`
- Lead upsert (dedupe by normalized URL, plus business-key dedupe for “no website” leads): `src/storage/leads.py`
- Runs helpers: `src/storage/runs.py`
- Seed CSV loader (keeps empty URL + supports column aliases): `src/url_loader.py`

Phase 2 — Scoring (completed)
- Heuristic scoring engine: `src/scoring.py`
  - Baseline 50 + PRD weights, clamp 0–100
  - Special rule (user decision): if URL missing, apply only +40 and ignore other rules
  - Recommendation includes top 2 reasons
- Tests: `tests/test_scoring.py`

Phase 3 — Scraping + Extraction (completed)
- Step 3.1 extraction contract (completed):
  - Uses `url` everywhere (not `website_url`)
  - Missing values are `null`
  - Enums:
    - `complexity`: basic/medium/complex/unknown
    - `load_speed`: fast/medium/slow/unknown
    - `platform`: wordpress/wix/squarespace/weebly/shopify/custom_html/custom_react/unknown
  - Code: `src/extraction_schema.py`
  - Tests: `tests/test_extraction_schema.py`
- Step 3.2 Playwright fetcher (completed):
  - Headless = true, timeout 45s, wait_until = networkidle, default UA
  - Returns rendered HTML + visible text with size caps
  - Code: `src/scraping/browser_fetch.py`
  - Smoke runner: `python -m src.scraping.smoke_fetch https://example.com`
- Step 3.3 LLM extraction (completed):
  - OpenAI Responses API client (stdlib): `src/llm/openai_responses.py`
  - Prompting + robust JSON parsing + schema validation: `src/llm_extraction.py`
  - Tests: `tests/test_llm_extraction_parsing.py`
- Step 3.4 Cost tracking (completed):
  - Token usage best-effort + env-priced estimate: `src/costing.py`
  - Optional hard stop: `--max-cost-usd` (requires `OPENAI_INPUT_COST_PER_1K`/`OPENAI_OUTPUT_COST_PER_1K`)

Phase 4 — Orchestration (completed)
- Pipeline runner: `main.py`
  - Modes:
    - normal: `--input <csv>`
    - rerun failed: `--only-failed`
  - Logging: console + `logs/run_<timestamp>.log` by default (`--log-file auto|none|<path>`)
  - Export: `exports/leads_<timestamp>.csv`

Phase 5 — Dashboard (completed)
- Streamlit dashboard: `dashboard.py`
  - Filters + table + metrics + histogram
  - Table click-to-select lead plus fallback selector
  - Lead detail + outreach draft
  - Actions: mark `outreach_sent`, capture `outreach_sent_at`, edit `notes`
  - Exports: “current view”, “all leads”, and “not contacted” CSVs to `exports/`

Phase 6 — Scheduling (completed)
- Cron example: `scripts/run_weekly.sh`
- GitHub Actions schedule: `.github/workflows/weekly.yml` (expects `secrets.OPENAI_API_KEY` + `business_urls.csv` in repo)

Phase 7 — Hardening + Tests (completed)
- CSV header validation (required columns/aliases): `src/url_loader.py`
- Upsert/dedupe test coverage: `tests/test_upsert_dedupe.py`
- URL loader validation tests: `tests/test_url_loader_validation.py`
- DB migration test coverage: `tests/test_db_migrations.py`
- Pricing presets for OpenAI models: `src/costing.py`
  - Built-in pricing for `gpt-4.1-nano`, `gpt-4o-mini`, `gpt-4.1-mini`, `gpt-4.1`
  - Manual override still supported via `OPENAI_INPUT_COST_PER_1K` / `OPENAI_OUTPUT_COST_PER_1K`

How to run quick checks
- Initialize DB: `python -m src.storage.init_db`
- Run tests: `python -m unittest discover -s tests`
- Run pipeline: `python main.py --input business_urls.csv --limit 200 --min-score-export 30`
- Run dashboard: `streamlit run dashboard.py`

Phase 9 — Free OpenStreetMap lead discovery (completed)
- Provider layer: `src/discovery/base.py` (`DiscoveryProvider` ABC + registry), `src/discovery/models.py` (`DiscoveryQuery`), `src/discovery/google.py` (deprecated Google adapter behind the same interface).
- Nominatim geocoding: `src/discovery/nominatim.py` — location → lat/lon + bbox, 1 req/s politeness, 24h disk cache, clear `ProviderError` on failure.
- Overpass discovery: `src/discovery/osm.py` — ~35 categories mapped to OSM tags (`CATEGORY_TAGS`, name-fallback), OverpassQL builder, element parsing (`contact:*`, website/address/email/phone), 7-day disk cache. Smoke runner: `python -m src.discovery.osm <category> <location> [limit]`.
- Shared transport: `src/discovery/_http.py` (`HttpBackoff` GET/POST with throttling + exponential retry), `src/discovery/cache.py` (`DiskCache`, deterministic hashed keys).
- Dedup/persistence: `candidate_to_seed` normalizes URL vs business identity; `src/storage/leads.py` + `db.py` migration persist osm_id/osm_type/address/lat/lon/opening_hours/country/source per lead (additive, no reset).
- CLI/dashboard: `main.py --provider {osm,google}` (default osm) + `--clear-cache`; manager picker in `dashboard.py`.
- No paid APIs or keys anywhere in the default path — discovery is fully free.
- Verified live: `python main.py --discover --category plumber --location "Austin, TX" --limit 5` found 2 plumbing businesses with url/phone/email + provenance; `--input business_urls.csv` CSV mode still completes end-to-end.
- Tests: `tests/test_overpass.py` (category/query/parse/cache/provider-error), updated `tests/test_discovery.py` (provider-based dedupe + google adapter), `tests/test_db_migrations.py` (new columns). Full suite: `python -m unittest discover -s tests` (45 tests, pass).

Phase 10 — Focused multi-page website crawling (completed)
- Page cache (in-memory + disk JSON, SHA-256 content hash): `src/scraping/page_cache.py`. Default store `data/crawl_cache/pages.json` (env `CRAWL_CACHE_DIR`/`CRAWL_CACHE_FILE`).
- Content extraction: `src/scraping/content_extractor.py` (boilerplate selectors removed, title/meta/canonical/headings/cleaned text, `extract_contact_clues`), trimming at paragraph boundaries in `src/scraping/content_merger.py` (`trim_text`, labelled `Section` merge, `content_hash`).
- Link extraction + ranking: `src/scraping/link_extractor.py` (same-domain, normalization/dedupe, asset/scheme filters) and `src/scraping/page_ranker.py` (positive/negative keyword scoring + anchor hints, deterministic `rank_pages`/`select_pages`).
- Crawler: `src/scraping/focused_crawler.py` — homepage + up to `MAX_CRAWL_PAGES-1` ranked pages (default 5 total, depth 1), sequential Playwright fetches, per-page failure tolerance, cache reuse, merged labelled doc + CONTACT section, step-by-step INFO logging, CLI smoke runner `python -m src.scraping.focused_crawler <url> [--pages N]`.
- Pipeline wiring (`main.py`): crawl on by default, `--no-crawl` restores homepage-only v1, `--clear-crawl-cache` empties the page cache; new `extract_lead_from_merged_content` in `src/llm_extraction.py` (same schema); `src/settings.py` crawl knobs.
- Fix: `src/llm/openai_responses.py` now sends Responses content blocks as `type: "input_text"` — the old `"text"` shape is rejected by the current API (affects both v1 and crawl paths; worth noting the account currently reports no credits / HTTP 429).
- Live fixture-site verification: home + about/services/contact/portfolio selected (privacy/blog skipped), 927 chars merged, second run reused 4 cached pages (visited=1), end-to-end pipeline run completes.
- Tests: 43 new across `tests/test_link_extractor.py`, `tests/test_page_ranker.py`, `tests/test_content_extractor.py`, `tests/test_content_merger.py`, `tests/test_focused_crawler.py`. Full suite: 88 tests pass.

Remaining nice-to-haves (Phase 10)
- Discovery UX: choose city/category in the dashboard and run it from the UI.
- Harder on OSM results — filter out closed/permanently-closed and low-signal businesses before scrape.
