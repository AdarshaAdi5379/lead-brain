# AGENTS.md

Lead-brain: local-lead finder for freelance web devs. Manual CSV (or OSM discovery) → Playwright fetch → LLM extract → deterministic scoring → SQLite → CSV exports → Streamlit dashboard, plus a local semantic search index and a grounded AI chat over the stored leads. Python 3.11, stdlib-only test stack.

## Commands

- Tests: `.venv/bin/python -m unittest discover -s tests` (stdlib `unittest`, no pytest). Single file: `.venv/bin/python -m unittest tests.test_scoring_dimensions`.
- No linters, formatters, or type checkers are configured. Verification = full test suite + `.venv/bin/python -m compileall -q main.py dashboard.py src` + a smoke run.
- Offline smoke (no API key, no crawl): `.venv/bin/python main.py --input business_urls.sample.csv --limit 3 --no-crawl --log-file none`
- Init/migrate DB: `.venv/bin/python -m src.storage.init_db`
- Dashboard: `streamlit run dashboard.py`
- Playwright (required for real fetching): `python -m playwright install --with-deps chromium`. Without it, the pipeline only processes no-website seeds via `_process_seed_no_fetch`.
- Search: the engine defaults to a stdlib hash embedder + SQLite store — zero extra deps. `requirements-search.txt` (sentence-transformers, chromadb) is optional; opt in via `.env` `SEARCH_EMBEDDER=sentence` / `SEARCH_VECTOR_STORE=chroma` ("auto" enables them when importable). Indexing runs at the end of every pipeline run — skip with `--no-index`, force a rebuild with `--rebuild-index`.

## Architecture

- Pipeline (`main.py` → `_run_seeds`, then `_export_csv_for_run`, then `_index_run_leads`): per seed — fingerprint (offline) → crawl (contact extraction runs inside on raw HTML) → SEO audit (offline) → visual audit (offline, screenshot-based) → LLM extraction → scoring (offline) → opportunity detection (offline) → `upsert_lead` (contact fields merged) → persist detections/audit/score/opportunities → CSV export → search index. No-website seeds take `_process_seed_no_fetch`, which still scores and derives contact fields from the CSV seed row.
- Deterministic engines — `src/fingerprinting/`, `src/seo/`, `src/scoring/`, `src/opportunities/`, `src/visual/`, `src/contact/`: pure functions, **no network, no LLM, no DB access**. The LLM only extracts; engine output reaches the LLM as neutral banner text (`to_llm_text`), never as instructions to infer.
- Contact engine (`src/contact/`): deterministic extraction of owner, address, postal code, opening hours, social URLs, contact page/form URLs, maps link, service areas. Runs inside the crawler on raw HTML **before** boilerplate removal (home + fetched + cached pages) so header/footer/form markup survives; merged via `ContactSignals`/`merge_contact_signals`; stored as lead columns (`service_areas` as JSON). Social URLs are the only contact facts shown to the LLM (neutral banner via `_crawl_summary`); the rest is deterministic-only.
- Visual audit (`src/visual/`): bounded offline audit (Playwright screenshots or reused cached HTML + CV-lite heuristics) after SEO and before extraction; multimodal summary gated behind `VISUAL_LLM_ENABLED`, degrades gracefully without an API key.
- `ScoringInputs` (`src/scoring/base.py`) is the shared input contract: main.py builds it once and feeds `score_site_lead` and `detect_opportunities`. All fields optional — engines must never crash on missing data (enforced by `test_scoring_missing_data.py`). No-website leads must produce empty/no-op engine results, not errors. `OpportunityReport.contact` carries input-derived contact context (website, phone, email, address, social URLs, primary contact, best contact method) for reporting only — it never affects scores.
- Engine tunables live in `ScoringConfig` / `OpportunityConfig` (`config.py`); no magic numbers in engine code. Detector order/registry: `src/opportunities/registry.py`.
- Every pipeline stage is wrapped in try/except — a failure never breaks the run; LLM extraction degrades to a failed-lead dict without `OPENAI_API_KEY`.
- Shared intelligence for search/chat/dashboard: `src/storage/search.py::leads_intelligence` returns per-lead `{lead, detections, seo, visual, score, opportunities}` dicts; the `lead` dict is `SELECT *` (all contact columns included, `service_areas` decoded). Builders consume these dicts, never raw SQL.
- Search (`src/search/`): one deterministic semantic document per lead (`build_lead_document`; labelled sections incl. contact info and `no phone`/`no email` markers; metadata whitelisted via `METADATA_KEYS`). `SearchService` is the facade; canonical storage is the `lead_embeddings` table; ranking lives in `ranking.py` — don't change similarity/ranking as a side effect of editing documents.
- Chat (`src/chat/`): grounded assistant over the same intelligence. `context_builder.build_lead_block` packs one lead into a compact block (cap `MAX_BLOCK_CHARS`); retrieved DB/crawl text is untrusted data (`safety.sanitize_text`, `<lead_data>` fence) and answers are checked by `validate_grounded_answer`. Synthesis backends (`CHAT_LLM_BACKEND`: auto/ollama/openai-compatible/none) use stdlib urllib only.
- Outreach (`src/outreach/context.py`): deterministic digest (`build_outreach_context`) shaped for a future outreach generator — it never writes email copy.
- Engines consume `ScoringInputs`-shaped dicts; per-page SEO signals live in `seo_audit["pages"]` (HTML-only aggregates like `pages_with_title` are only meaningful when `html_pages > 0`; legacy text-only cached pages are excluded, never counted as missing).

## DB conventions (src/storage/)

- Schema: `SCHEMA_SQL` in `src/storage/db.py` (`CREATE TABLE IF NOT EXISTS`) plus additive `ALTER TABLE` migrations in `_apply_migrations` (`_ADDITIVE_LEAD_COLUMNS`). **Adding a column requires both** — existing DBs (`data/leads.sqlite`) only get it via the migration.
- Per-lead rows use delete-then-insert `replace_*` (detections, seo audit, visual audit, `lead_scores`, `business_opportunities`) so re-runs stay consistent.
- After `upsert_lead`, look up `lead_id` via `get_lead_id_by_url(normalize_url_for_dedupe(url))` — upsert dedupes by normalized URL.
- Storage modules decode JSON columns into list/dict keys (e.g. `evidence`, `recommended_services`, `service_areas`) but keep the raw `*_json` keys; CSV export merges via `csv_fields_from_row`-style helpers and joins `service_areas_json` with `"; "`.

## Repo conventions

- Commit style: `feat(<area>): ...` (see `git log`: fingerprinting/seo/scoring/opportunities/visual/chat/search/contact). Commit message wording has been exact in past features — keep the requested message verbatim.
- Never commit generated/private files: `data/`, `exports/`, `logs/`, `.env`, `business_urls.csv` (all gitignored). Exception: `src/fingerprinting/data/` ships in the repo (`.gitignore` un-hides it) — the fingerprint catalog is code.
- Every file starts with `from __future__ import annotations`.
- All LLM HTTP calls use stdlib `urllib` (`src/llm/openai_responses.py` for extraction, `src/chat/llm.py` for chat) — there is no `openai`/`ollama` pip dependency.
- Tests: stdlib `unittest`, no network, no browser. Shared synthetic fixtures: `tests/scoring_fixtures.py`, `tests/opportunity_fixtures.py`, `tests/search_fixtures.py` (`SearchTestDb`: temp DB + `add_lead`/`add_contact`/`add_seo`/… helpers), `tests/chat_fixtures.py`, `tests/contact_fixtures.py`, `tests/visual_fixtures.py`. Tests must be runnable with zero env/API keys; importing `main.py`/`dashboard.py` in tests is safe offline (playwright/streamlit load locally, no browser needed).
- `OPENAI_API_KEY` in `.env` for extraction; pricing env vars only needed with `--max-cost-usd`.
- Weekly CI exists (`.github/workflows/weekly.yml`) — runs the full pipeline with `business_urls.csv`; not part of the local dev loop.
