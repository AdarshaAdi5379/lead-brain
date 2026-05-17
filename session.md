Session Notes — lead-brain
Last updated: 2026-05-18 (Asia/Kolkata)

Repo
- GitHub: `AdarshaAdi5379/lead-brain`
- Default branch: `main`

What’s implemented so far

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
- Lead upsert (dedupe by normalized URL): `src/storage/leads.py`
- Seed CSV loader (keeps empty URL + supports column aliases): `src/url_loader.py`

Phase 2 — Scoring (completed)
- Heuristic scoring engine: `src/scoring.py`
  - Baseline 50 + PRD weights, clamp 0–100
  - Special rule (user decision): if URL missing, apply only +40 and ignore other rules
  - Recommendation includes top 2 reasons
- Tests: `tests/test_scoring.py`

Phase 3 — Scraping (in progress)
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

How to run quick checks
- Initialize DB: `python -m src.storage.init_db`
- Run tests: `python -m unittest discover -s tests`

Next step (do next session)
Phase 3 — Step 3.3: LLM extraction prompt + response parsing
- Build a module that:
  1) takes `FetchResult` (html + text)
  2) calls OpenAI (model: GPT‑4.1 Nano preferred; fallback GPT‑4o‑mini)
  3) requests strict JSON matching `ExtractedLead` contract (`src/extraction_schema.py`)
  4) parses and validates via `validate_extracted_lead`
  5) sets `extraction_success` + `last_error` cleanly
- Follow-up steps after 3.3:
  - Step 3.4 cost tracking
  - Phase 4 pipeline (`main.py`)
  - Phase 5 Streamlit dashboard

Open decisions / required inputs for Phase 3.3
- OpenAI API setup:
  - Confirm where to read the API key from (`.env` with `OPENAI_API_KEY` recommended)
  - Confirm model string to use for “GPT‑4.1 Nano” in code (we’ll wire it exactly to the official name you want)
- Token budget strategy:
  - Prefer sending visible text + key HTML snippets instead of full HTML if size is huge

