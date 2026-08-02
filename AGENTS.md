# AGENTS.md

Lead-brain: local-lead finder for freelance web devs. Manual CSV (or OSM discovery) → Playwright fetch → LLM extract → deterministic scoring → SQLite → CSV exports → Streamlit dashboard. Python 3.11, stdlib-only test stack.

## Commands

- Tests: `.venv/bin/python -m unittest discover -s tests` (stdlib `unittest`, no pytest). Single file: `-m unittest tests.test_scoring_dimensions`.
- No linters, formatters, or type checkers are configured. Verification = full test suite + `python -m compileall -q main.py dashboard.py src` + a smoke run.
- Offline smoke (no API key, no crawl): `.venv/bin/python main.py --input business_urls.sample.csv --limit 3 --no-crawl --log-file none`
- Init/migrate DB: `.venv/bin/python -m src.storage.init_db`
- Dashboard: `streamlit run dashboard.py`
- Playwright (required for real fetching): `python -m playwright install --with-deps chromium`. Without it, the pipeline only processes no-website seeds via `_process_seed_no_fetch`.

## Architecture

- Pipeline entrypoint: `main.py` → `_run_seeds` → per seed: fingerprint (offline) → crawl → SEO audit (offline) → `visual audit` (offline, screenshot-based) → LLM extraction → scoring (offline) → opportunity detection (offline) → `upsert_lead` → persist detections/audit/score/opportunities → CSV export (`_export_csv_for_run`).
- Four deterministic engines — `src/fingerprinting/`, `src/seo/`, `src/scoring/`, `src/opportunities/`: pure functions, **no network, no LLM, no DB access**. The LLM only extracts; engine output reaches the LLM as neutral banner text (`to_llm_text`), never as instructions to infer.
- Added in Phase 11: `src/visual/` runs a bounded, offline visual quality audit (Playwright screenshots or reused cached HTML + deterministic CV-lite heuristics) after the SEO audit and before LLM extraction; its findings reach the LLM only as neutral banner text (`src/visual/report.py::to_llm_text`), never as inference prompts. The optional multimodal summary is gated behind `VISUAL_LLM_ENABLED` and degrades gracefully without an API key.
- `ScoringInputs` (`src/scoring/base.py`) is the shared input contract: main.py builds it once and feeds `score_site_lead` and `detect_opportunities`. All fields optional — engines must never crash on missing data (enforced by `test_scoring_missing_data.py`). No-website leads must produce empty/no-op engine results, not errors.
- Engine tunables live in `ScoringConfig` / `OpportunityConfig` (`config.py`); no magic numbers in engine code. Detector order/registry: `src/opportunities/registry.py`.
- Every pipeline stage (fingerprint, crawl, audit, scoring, opportunities, persistence) is wrapped in try/except — a failure never breaks the run; LLM extraction degrades to a failed-lead dict without `OPENAI_API_KEY`.
- Engines consume `ScoringInputs`-shaped dicts; per-page SEO signals live in `seo_audit["pages"]` (HTML-only aggregates like `pages_with_title` are only meaningful when `html_pages > 0`; legacy text-only cached pages are excluded, never counted as missing).

## DB conventions (src/storage/)

- Schema: `SCHEMA_SQL` in `src/storage/db.py` (`CREATE TABLE IF NOT EXISTS`) plus additive `ALTER TABLE` migrations in `_apply_migrations`. **Adding a column requires both** — existing DBs (`data/leads.sqlite`) only get it via the migration.
- Per-lead rows use delete-then-insert `replace_*` (detections, seo audit, visual audit, `lead_scores`, `business_opportunities`) so re-runs stay consistent.
- After `upsert_lead`, look up `lead_id` via `get_lead_id_by_url(normalize_url_for_dedupe(url))` — upsert dedupes by normalized URL.
- Storage modules decode JSON columns into list/dict keys (e.g. `evidence`, `recommended_services`) but keep the raw `*_json` keys; CSV export merges via `csv_fields_from_row`-style helpers.

## Repo conventions

- Commit style: `feat(<area>): ...` (see `git log`: fingerprinting/seo/scoring/opportunities). Commit message wording has been exact in past features — keep the requested message verbatim.
- Never commit generated/private files: `data/`, `exports/`, `logs/`, `.env`, `business_urls.csv` (all gitignored). Exception: `src/fingerprinting/data/` ships in the repo (`.gitignore` un-hides it) — the fingerprint catalog is code.
- Every file starts with `from __future__ import annotations`.
- Tests: stdlib `unittest`, no network, synthetic fixture modules (`tests/scoring_fixtures.py`, `tests/opportunity_fixtures.py`) shared across test files. Tests must be runnable with zero env/API keys.
- `OPENAI_API_KEY` in `.env` for extraction; pricing env vars only needed with `--max-cost-usd`.
- Weekly CI exists (`.github/workflows/weekly.yml`) — runs the full pipeline with `business_urls.csv`; not part of the local dev loop.
