TODO – Second Brain Lead Finder (v1)
Date: May 2026
Goal: Implement in small, verifiable steps (finish one step before starting the next).

How to use this file
- Work top-to-bottom.
- Only start the next step after the current step passes its “Done when” checks.
- Keep v1 minimal: manual CSV input → scrape → score → SQLite → CSV export → Streamlit dashboard.

Progress (implemented)
- ✅ Phase 0 (Repo/Env): Steps 0.1–0.2 completed
- ✅ Phase 1 (Storage): Steps 1.1–1.3 completed
- ✅ Phase 2 (Scoring): Step 2.1 completed
- ✅ Phase 3 (Scraping/Extraction): Steps 3.1–3.4 completed
- ✅ Phase 4 (Pipeline): Steps 4.1–4.3 completed
- ✅ Phase 5 (Dashboard): Steps 5.1–5.4 completed
- ✅ Phase 6 (Scheduling): Step 6.1 completed
- ✅ Phase 7 (Hardening/Tests): Steps 7.1–7.2 completed
- ✅ Phase 8 (Lead Discovery via Google Places API): Steps 8.1–8.6 completed

---

PHASE 0 — Repo + Environment (one-time)

Step 0.1 — Create project skeleton
Tasks
- Create folders: `src/`, `data/`, `exports/`, `logs/` (if you want logs on disk).
- Add `.gitignore` for: `__pycache__/`, `.venv/`, `*.sqlite`, `exports/*.csv`, `logs/*.log`, `.env`.
- Add `README.md` with basic run commands.
Done when
- Repo has predictable structure and ignores generated files.
Status
- ✅ Done

Step 0.2 — Python environment + dependencies
Tasks
- Add `requirements.txt` (or `pyproject.toml`) with:
  - `streamlit`, `pandas`, `plotly`, `python-dotenv`
  - scraping stack (choose one for v1):
    - Option A: `scrapegraphai` + `playwright`
    - Option B (fallback): `playwright` + direct OpenAI calls
- Add a `.env.example` containing: `OPENAI_API_KEY=...`
Done when
- `pip install -r requirements.txt` works.
- `playwright install` works (if Playwright is used).
Status
- ✅ Done

---

PHASE 1 — Data Model + Storage (SQLite)

✅ Step 1.1 — Define DB schema and migrations (simple)
Tasks
- Decide DB path (suggestion: `data/leads.sqlite`).
- Create a `storage` module that:
  - creates tables if missing
  - opens/closes connections safely
- Tables (v1):
  - `leads` (from PRD Section 8)
  - `scraping_runs` (from PRD Section 8)
Notes (implemented)
- Schema created in `src/storage/db.py`
- DB path configured in `src/settings.py` (`data/leads.sqlite`)
Done when
- Running `python -m src.storage.init_db` creates `data/leads.sqlite`
Done when
- Running a small script creates `data/leads.sqlite` with both tables.

✅ Step 1.2 — Implement lead upsert + dedupe by normalized URL
Tasks
- Upsert policy: `website_url` is unique key.
- On repeat URL: update fields + `extracted_at`, do not create new row.
- Store failures too (`extraction_success = 0`, with minimal metadata).
Notes (implemented)
- Dedupe key is `leads.website_url_normalized` (UNIQUE index)
- URL normalization in `src/storage/normalization.py`
- Upsert in `src/storage/leads.py`
Done when
- A quick test inserts the same URL twice and DB still has 1 row updated.

✅ Step 1.3 — CSV import for seed URLs (with aliases)
Tasks
- Parse input CSV with columns:
  - `business_name`, `category`, `url`, `city`, `state`
- Normalize:
  - trim whitespace
  - ensure URL has scheme (`http://` / `https://`) if missing
  - keep empty URLs (store as `url=None`) so the pipeline can treat them as “No website URL found”
  - accept alternate column names (e.g. `Company`, `Website`, etc.)
Notes (implemented)
- Loader implemented in `src/url_loader.py`
Done when
- Importing a sample CSV returns a clean list of seed rows.

---

PHASE 2 — Scoring Engine (pure Python, no APIs)

✅ Step 2.1 — Implement scoring rules from PRD Section 7
Tasks
- Function: `score_lead(extracted_fields) -> {score, priority, recommendation}`
- Baseline 50, apply weights, clamp 0–100.
- Priority labels:
  - Hot ≥ 70
  - Warm 50–69
  - Cold 30–49
  - Avoid < 30
- Recommendation text (simple mapping by priority).
Notes (implemented)
- Scoring in `src/scoring.py` with top-2 reasons in recommendation
- Special rule: if no website URL, apply only +40 and ignore other rules
- Tests: `tests/test_scoring.py`
Done when
- Unit test / sample script prints expected scores for a few canned examples.

---

PHASE 3 — Scraping + Extraction (Playwright + LLM)

✅ Step 3.1 — Define extraction JSON contract
Tasks
- Final extracted fields per URL (v1):
  - `business_name`
  - `phone`
  - `email`
  - `url`
  - `platform` (WordPress/Wix/custom HTML/etc.)
  - `complexity` (basic/medium/complex)
  - `load_speed` (fast/medium/slow)
  - `extraction_success` (bool)
  - optional: `error_reason`
Notes (implemented)
- Contract + validator in `src/extraction_schema.py`
- Enums for `platform`, `complexity`, `load_speed` include `unknown`
- Tests: `tests/test_extraction_schema.py`
Done when
- There is a single authoritative schema (dataclass / pydantic model / dict spec).

✅ Step 3.2 — Fetch rendered HTML with Playwright
Tasks
- Headless browsing:
  - timeout per site (e.g., 30–45s)
  - wait strategy (e.g., `networkidle` or a fixed delay)
- Rate limiting: default 1 second delay between sites.
- Failure handling:
  - timeout / DNS / 404 → mark failed and continue
  - basic detection: if page empty / blocked
Notes (implemented)
- Fetcher: `src/scraping/browser_fetch.py` (headless, 45s, `networkidle`, returns both HTML + visible text)
- Smoke runner: `python -m src.scraping.smoke_fetch <url>`
Done when
- A script can load 3–5 URLs and save their HTML/text length metrics.

✅ Step 3.3 — LLM extraction prompt + response parsing
Tasks
- Send page content to OpenAI model (as per PRD: GPT‑4.1 Nano; fallback GPT‑4o‑mini).
- Prompt must request strictly JSON output matching the schema.
- Parse JSON robustly:
  - handle invalid JSON (mark extraction failed)
  - sanitize phone/email with regex checks
Done when
- For 5 sample sites, you get structured JSON with phone/email present where available.
Notes (implemented)
- `src/llm_extraction.py` (prompting + robust JSON parsing + sanitization + schema validation)
- `src/llm/openai_responses.py` (minimal Responses API client)
- Tests: `tests/test_llm_extraction_parsing.py`

✅ Step 3.4 — Cost tracking (estimate)
Tasks
- Capture input/output token usage per call (if API returns it).
- Maintain running total per run.
- Hard stop option: stop scraping when estimated cost exceeds `$X`.
Done when
- End of run prints: total URLs, successes, failures, estimated cost.
Notes (implemented)
- Token usage captured when returned by API; cost estimated via env vars:
  - `OPENAI_INPUT_COST_PER_1K`
  - `OPENAI_OUTPUT_COST_PER_1K`
- Hard stop: `--max-cost-usd` (requires pricing configured)

---

PHASE 4 — Orchestration (main pipeline)

✅ Step 4.1 — Create `main.py` pipeline runner
Tasks
- CLI args (keep minimal):
  - `--input business_urls.csv`
  - `--min-score-export 30`
  - `--limit 200` (optional)
- Run flow:
  1) start `scraping_runs` row
  2) read CSV seeds
  3) for each URL: scrape → extract → score → upsert lead
  4) finalize `scraping_runs` row
  5) export CSV
Done when
- `python main.py --input business_urls.csv` completes and writes DB + export.
Notes (implemented)
- `--only-failed` rerun mode supported
- Optional `.env` loading (if `python-dotenv` installed)

✅ Step 4.2 — Export CSV (timestamped)
Tasks
- Create `exports/` if missing.
- Export filtered set (default: score ≥ 30) to:
  - `exports/leads_<YYYYMMDD_HHMMSS>.csv`
- Columns: flattened leads excluding internal IDs if desired.
Done when
- Export file exists and opens correctly in a spreadsheet.

✅ Step 4.3 — Logging
Tasks
- Log to console + optional `logs/run_<timestamp>.log`.
- Record:
  - start/end time
  - URL count
  - errors per URL
  - cost estimate
Done when
- You can see which URLs failed and why without rerunning.
Notes (implemented)
- Logs to console + `logs/run_<timestamp>.log` by default (`--log-file auto|none|<path>`)

---

PHASE 5 — Streamlit Dashboard

✅ Step 5.1 — Read-only DB queries + basic UI
Tasks
- Create `dashboard.py`:
  - connects to SQLite
  - loads leads into a dataframe
  - sidebar filter: min score, max rows
  - table with key columns (name/phone/email/url/score/priority/platform)
Done when
- `streamlit run dashboard.py` shows filtered leads table.

✅ Step 5.2 — Metrics + histogram
Tasks
- Metrics cards:
  - total leads in current view
  - hot leads count
  - average score
  - total leads in DB
- Plotly histogram of score distribution.
Done when
- Metrics and chart update when filters change.

✅ Step 5.3 — Lead detail + outreach template generator
Tasks
- Select lead (dropdown or table selection).
- Show full extracted data.
- Generate outreach email text using lead signals:
  - missing/slow/basic platform → mention politely
  - CTA and next step
- Provide editable textarea for copy/paste.
Done when
- You can pick any lead and get a usable personalized email draft.
Notes (implemented)
- Also supports marking `outreach_sent` and editing `notes` in DB

✅ Step 5.4 — Dashboard CSV export buttons
Tasks
- “Export Current View” button → creates a CSV from the filtered dataframe.
- “Export All Leads” button → exports entire DB.
Done when
- Both buttons produce files in `exports/` (timestamped).

---

PHASE 6 — Scheduling (Optional for v1)

✅ Step 6.1 — Cron/GitHub Actions template
Tasks
- Add a `scripts/` example:
  - `run_weekly.sh` or GitHub Actions YAML schedule
- Document recommended cadence (weekly).
Done when
- You can schedule `python main.py --input ...` without manual edits.
Notes (implemented)
- `scripts/run_weekly.sh`
- `.github/workflows/weekly.yml`

---

PHASE 7 — Hardening + Quality

✅ Step 7.1 — Input validation + safety limits
Tasks
- Validate CSV columns exist.
- Limit max URLs per run (default 200).
- Add `--only-failed` re-run option (optional).
Done when
- Script fails fast with clear errors for bad input and never runs unbounded.
Notes (implemented)
- CSV header validation in `src/url_loader.py`
- `--limit` capped at 1000
- `--only-failed` rerun mode in `main.py`

✅ Step 7.2 — Minimal tests (only for scoring/storage)
Tasks
- Add small tests for:
  - scoring weights + clamping
  - upsert/dedup behavior
Done when
- `python -m unittest` (or pytest) passes locally.
Notes (implemented)
- Added tests for URL loader validation and upsert/dedupe (`tests/test_url_loader_validation.py`, `tests/test_upsert_dedupe.py`)

---

PHASE 8 — Lead Discovery (Google Places API)

Goal
- Add an automatic lead-discovery step so the app can find businesses, names, websites, and contact details without manual CSV entry.
- Use the Google Places API key as the discovery source, then feed discovered websites into the existing scrape → extract → score pipeline.

Step 8.1 — Add discovery configuration
Tasks
- Add env settings for Google Places:
  - `GOOGLE_MAPS_API_KEY`
  - optional `GOOGLE_PLACES_TEXT_SEARCH_RADIUS`
  - optional `GOOGLE_PLACES_LANGUAGE`
- Decide discovery input format:
  - city + category
  - keyword + location
  - or a batch CSV of discovery queries
Done when
- The app can read Google Places credentials from `.env` and has a clear discovery mode configuration.
Status
- ✅ Done
- Code: `src/settings.py` (GOOGLE_MAPS_API_KEY, PLACES_TEXT_SEARCH_RADIUS, PLACES_LANGUAGE)

Step 8.2 — Query Google Places for candidates
Tasks
- Search for businesses by category and location.
- Collect structured fields from the search response:
  - business name
  - place id
  - address
  - phone if available
  - rating / review count if available
  - website URL if available
- Keep raw Google result metadata for traceability.
Done when
- A discovery run returns a list of candidate businesses for one city/category query.
Status
- ✅ Done
- Code: `src/discovery/places.py` (`text_search` + `place_details`)

Step 8.3 — Fetch place details and websites
Tasks
- For each discovered place:
  - fetch place details
  - extract the website URL
  - keep phone/address/location fields
- Normalize URLs before handing them to the website scraper.
- Skip or flag entries that do not have a website.
Done when
- Discovered businesses include website URLs whenever Google provides them.
Status
- ✅ Done
- Code: `src/discovery/places.py` (place_details with website field)

Step 8.4 — Convert discovery results into seed leads
Tasks
- Transform Google results into the same seed structure the existing pipeline expects.
- Option A: write discovered rows to a CSV for the current pipeline.
- Option B: insert discovered rows directly into SQLite and let the pipeline process them.
- Preserve de-duplication using normalized website URL.
Done when
- Discovered rows can enter the existing scrape/extract/score flow without manual copying.
Status
- ✅ Done
- Code: `src/discovery/discovery.py` (`discover_to_seeds`, `discover_leads`)

Step 8.5 — Add discovery-driven run mode
Tasks
- Add a new mode for:
  - `city + category` discovery
  - `category + region` discovery
- Keep the existing manual CSV pipeline working.
- Make discovery mode produce:
  - discovered businesses
  - exported seed CSV or DB rows
  - downstream lead scores
Done when
- You can run one command to discover new leads and process them end-to-end.
Status
- ✅ Done
- Code: `main.py` (`--discover`, `--category`, `--location`, `--discover-queries`)

Step 8.6 — Add tests and validation
Tasks
- Validate API errors and empty results cleanly.
- Test URL normalization and dedupe for discovered leads.
- Test the discovery-to-seed conversion format.
Done when
- Discovery mode fails clearly on bad input and passes basic automated tests.
Status
- ✅ Done
- Tests: `tests/test_discovery.py` (9 tests)

Notes
- This feature should be treated as a new lead source, not a replacement for the existing extraction pipeline.
- Google Places is the recommended discovery source because it is more structured and reliable than scraping Google Maps pages directly.

---

Remaining optional improvements
- Dashboard: table click-to-select lead (instead of dropdown)
- Pricing presets per model (avoid manual env price config)
- Outreach workflow: sent timestamp + “not contacted” exports
