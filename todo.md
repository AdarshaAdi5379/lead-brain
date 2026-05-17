TODO – Second Brain Lead Finder (v1)
Date: May 2026
Goal: Implement in small, verifiable steps (finish one step before starting the next).

How to use this file
- Work top-to-bottom.
- Only start the next step after the current step passes its “Done when” checks.
- Keep v1 minimal: manual CSV input → scrape → score → SQLite → CSV export → Streamlit dashboard.

Progress (implemented)
- ✅ Phase 1 (Storage): Steps 1.1–1.3 completed
- ✅ Phase 2 (Scoring): Step 2.1 completed
- ✅ Phase 3 (Scraping): Steps 3.1–3.2 completed

---

PHASE 0 — Repo + Environment (one-time)

Step 0.1 — Create project skeleton
Tasks
- Create folders: `src/`, `data/`, `exports/`, `logs/` (if you want logs on disk).
- Add `.gitignore` for: `__pycache__/`, `.venv/`, `*.sqlite`, `exports/*.csv`, `logs/*.log`, `.env`.
- Add `README.md` with basic run commands.
Done when
- Repo has predictable structure and ignores generated files.

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

Step 3.3 — LLM extraction prompt + response parsing
Tasks
- Send page content to OpenAI model (as per PRD: GPT‑4.1 Nano; fallback GPT‑4o‑mini).
- Prompt must request strictly JSON output matching the schema.
- Parse JSON robustly:
  - handle invalid JSON (mark extraction failed)
  - sanitize phone/email with regex checks
Done when
- For 5 sample sites, you get structured JSON with phone/email present where available.

Step 3.4 — Cost tracking (estimate)
Tasks
- Capture input/output token usage per call (if API returns it).
- Maintain running total per run.
- Hard stop option: stop scraping when estimated cost exceeds `$X`.
Done when
- End of run prints: total URLs, successes, failures, estimated cost.

---

PHASE 4 — Orchestration (main pipeline)

Step 4.1 — Create `main.py` pipeline runner
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

Step 4.2 — Export CSV (timestamped)
Tasks
- Create `exports/` if missing.
- Export filtered set (default: score ≥ 30) to:
  - `exports/leads_<YYYYMMDD_HHMMSS>.csv`
- Columns: flattened leads excluding internal IDs if desired.
Done when
- Export file exists and opens correctly in a spreadsheet.

Step 4.3 — Logging
Tasks
- Log to console + optional `logs/run_<timestamp>.log`.
- Record:
  - start/end time
  - URL count
  - errors per URL
  - cost estimate
Done when
- You can see which URLs failed and why without rerunning.

---

PHASE 5 — Streamlit Dashboard

Step 5.1 — Read-only DB queries + basic UI
Tasks
- Create `dashboard.py`:
  - connects to SQLite
  - loads leads into a dataframe
  - sidebar filter: min score, max rows
  - table with key columns (name/phone/email/url/score/priority/platform)
Done when
- `streamlit run dashboard.py` shows filtered leads table.

Step 5.2 — Metrics + histogram
Tasks
- Metrics cards:
  - total leads in current view
  - hot leads count
  - average score
  - total leads in DB
- Plotly histogram of score distribution.
Done when
- Metrics and chart update when filters change.

Step 5.3 — Lead detail + outreach template generator
Tasks
- Select lead (dropdown or table selection).
- Show full extracted data.
- Generate outreach email text using lead signals:
  - missing/slow/basic platform → mention politely
  - CTA and next step
- Provide editable textarea for copy/paste.
Done when
- You can pick any lead and get a usable personalized email draft.

Step 5.4 — Dashboard CSV export buttons
Tasks
- “Export Current View” button → creates a CSV from the filtered dataframe.
- “Export All Leads” button → exports entire DB.
Done when
- Both buttons produce files in `exports/` (timestamped).

---

PHASE 6 — Scheduling (Optional for v1)

Step 6.1 — Cron/GitHub Actions template
Tasks
- Add a `scripts/` example:
  - `run_weekly.sh` or GitHub Actions YAML schedule
- Document recommended cadence (weekly).
Done when
- You can schedule `python main.py --input ...` without manual edits.

---

PHASE 7 — Hardening + Quality

Step 7.1 — Input validation + safety limits
Tasks
- Validate CSV columns exist.
- Limit max URLs per run (default 200).
- Add `--only-failed` re-run option (optional).
Done when
- Script fails fast with clear errors for bad input and never runs unbounded.

Step 7.2 — Minimal tests (only for scoring/storage)
Tasks
- Add small tests for:
  - scoring weights + clamping
  - upsert/dedup behavior
Done when
- `python -m unittest` (or pytest) passes locally.

---

Next step to start with (recommended)
- Step 0.1 (project skeleton)
