Session Notes — lead-brain
Last updated: 2026-05-18 (Asia/Kolkata)

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
  - Lead detail + outreach draft
  - Actions: mark `outreach_sent`, edit `notes`
  - Exports: “current view” + “all leads” to `exports/`

Phase 6 — Scheduling (completed)
- Cron example: `scripts/run_weekly.sh`
- GitHub Actions schedule: `.github/workflows/weekly.yml` (expects `secrets.OPENAI_API_KEY` + `business_urls.csv` in repo)

Phase 7 — Hardening + Tests (completed)
- CSV header validation (required columns/aliases): `src/url_loader.py`
- Upsert/dedupe test coverage: `tests/test_upsert_dedupe.py`
- URL loader validation tests: `tests/test_url_loader_validation.py`

How to run quick checks
- Initialize DB: `python -m src.storage.init_db`
- Run tests: `python -m unittest discover -s tests`
- Run pipeline: `python main.py --input business_urls.csv --limit 200 --min-score-export 30`
- Run dashboard: `streamlit run dashboard.py`

Remaining nice-to-haves
- Pricing presets per model (avoid manual env price config).
- Dashboard: table click-to-select lead (instead of dropdown).
- Outreach workflow: sent timestamp + “not contacted” exports.
