Session Notes — lead-brain
Last updated: 2026-08-26 (Asia/Kolkata)

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

Phase 11 — Local Visual Website Audit (completed)
- Offline, local screenshot-based visual quality audit. Playwright (or cached HTML) renders pages; `src/visual/capture.py` captures bounded desktop + mobile screenshots (max `max_screenshots=5` per lead, viewport + pixel caps in `src/visual/config.py`).
- Deterministic computer-vision-lite heuristics over screenshots (`src/visual/heuristics.py`): ink ratio, contrast, row/col variance, region count, dominant-color share, mobile viewport; fixed an `_grid_sample` out-of-bounds read and replaced deprecated Pillow `getdata()` with `get_flattened_data` (compat shim).
- Signals (`src/visual/signals.py`): modern/outdated design, clutter, weak hierarchy, weak mobile, weak/strong CTA, strong brand, responsive, low contrast. Additive weighted scoring with sub-qualities (layout/readability/branding/mobile/conversion), `score_page`/`score_site`/`label_for_score` in `src/visual/score.py`; health bands Excellent≥85 / Good≥70 / Fair≥50 / Poor≥30.
- Report (`src/visual/report.py`): `build_report` → `VisualAuditReport` (site counts, summary, `csv_fields`/`csv_fields_from_row`, `to_llm_text` neutral banner); optional multimodal summary in `src/visual/summarizer.py` (gated by `VISUAL_LLM_ENABLED`, degrades gracefully without an API key).
- Storage (`src/storage/db.py`, `src/storage/visual.py`): `visual_audits` + `visual_page_audits` tables (additive `llm_summary` migration), delete-then-insert persistence, per-lead lookups (`audits_by_lead`, `page_audits_for_audit`).
- Pipeline wiring (`main.py`): `run_visual_audit` runs after the SEO audit and before LLM extraction, gated by `visual_config.enabled` and fetch success; no-website/failed-fetch seeds yield no-op results and never break the run. The neutral `to_llm_text` banner reaches the LLM as context only. Dashboard (`dashboard.py`) sidebar filters: Visual health, min visual score, weak mobile, clutter, weak CTA, strong branding.
- Verified offline: `python main.py --input business_urls.sample.csv --limit 3 --no-crawl --log-file none` ran the visual audit (example.com → 98/100 Excellent) and completed end-to-end.
- Tests: 10 new files (`tests/test_visual_*.py` + `tests/visual_fixtures.py`); full suite 338 tests pass (`python -m unittest discover -s tests`).

Phase 14 — Local semantic search engine (completed)
- Fully offline index + search: `src/search/` (config, index, embedding, vector_store, query, ranking, summarizer, cache, search_service).
- `lead_embeddings` table, incremental `index_run`/`index_lead` on every pipeline run (content-hash skipped), `--no-index`, `--rebuild-index`.
- Deterministic `hash-ngram-512` embedder + SQLite cosine store (no deps); optional sentence-transformers + Chroma.
- AI Search dashboard page: hybrid/semantic/keyword, whitelisted filters, similar-leads, per-lead AI context.
- Tests: `tests/test_search_*.py` + `tests/search_fixtures.py`.

Phase 15 — Grounded AI chat assistant over leads (completed)
- New `src/chat/` package (stdlib only, no paid APIs): base/config/safety/router/retriever/context_builder/prompts/llm/memory/response/service.
- `route_query` — deterministic local intent router (8 intents) over keyword/regex + DB-derived hints (categories/cities/states/countries/platforms/business names); extracts top-N, priority bands, score thresholds, weak-SEO/visual signals, no-website, platform, place, business names (multi-name for compare).
- `LeadRetriever` — semantic path reuses `SearchService` (validate_filters whitelist); SQL fallback (`_sql_select_leads`, parameterized, deterministic ORDER BY lead score → top opp → contactability → recency) when the index is empty; SQL accepts list filters via `IN` where the vector engine accepts only scalars; similarity fallback ranks same-category first; filter merge UI-wins.
- `ResponseGenerator` — retrieval-summary bullets, compare markdown table, rich lead-detail block, no-data message; optional RAG synthesis through `LLMBackend` (Ollama `/api/chat` or OpenAI-compatible `/v1/chat/completions`, stdlib urllib, 30s probe TTL, never raises) with grounding guard: quoted unknown names are rejected, and an answer with no lead/digit reference is rejected → automatic fallback to the deterministic mode.
- Safety: `<lead_data>` untrusted-data fence, prompt injection defense, `sanitize_text`/`redact`, source panel carries rationale; stored site text is data, never instructions.
- `ChatService` facade: `ask`/`retrieve_context`/`summarize_lead`/`find_similar`/`compare`/`explain_ranking`/`backend_status`; persisted sessions (`chat_sessions`/`chat_messages` in `SCHEMA_SQL`, additive), session restore via `last_session`/`load_history`, `clear_session`. `ask` never raises — failures degrade to a no-data response.
- Dashboard AI Chat page (`dashboard.py` radio "AI Chat"): st.chat_input conversation, mode badge, sources expander, chat filters sidebar, backend status, clear conversation; last session restored on load.
- Env tunables: `CHAT_*` in `src/settings.py` (CHAT_LLM_BACKEND auto/ollama/openai/none, Ollama + OpenAI-compatible URLs/models, timeouts, context budget, history, persistence, top-k).
- Verified offline (no LLM, no index): summarization, compare table, detail, no-data, no-website, RAG pass/fallback/hallucination with a fake backend, memory persistence round-trip.
- Tests: 7 new files (`tests/test_chat_*.py` + `tests/chat_fixtures.py`); full suite 561 tests pass.

Phase 12 — Contact intelligence extraction engine (completed)
- Deterministic contact extraction: `src/contact/` (extractor, forms, helpers, jsonld, schema, social) runs inside the crawler on **raw HTML before boilerplate removal** (home + fetched + cached pages) so header/footer/form markup survives.
- Extracts: owner name, address, postal code, opening hours, social URLs, contact page/form URLs, maps link, service areas (the area served). JSON-LD (`@type` LocalBusiness/…), `mailto:`/`tel:`/bare email + phone regex, address/social/forms heuristics; merged via `ContactSignals`/`merge_contact_signals`.
- Persistence: additive migration adds contact columns to `leads` (incl. `service_areas` JSON, `social_urls` JSON) — no DB reset needed; upsert merges new facts over existing ones; seed CSV rows contribute `service_areas`/contact fields for no-website leads.
- Wired into `main.py` per-seed flow and `focused_crawler.py` (`run_contact_extraction` on merged cached/pages HTML); no-website/failed seeds yield no-op signals, never errors.
- Tests: `tests/contact_fixtures.py`, `tests/test_contact_extractor.py`, `tests/test_db_migrations.py` (new columns), `tests/test_focused_crawler.py`, `tests/test_upsert_dedupe.py`; full suite 592 tests pass. Commit `8f77c6d`.

Phase 13 — Contact intelligence across the platform (completed)
- `src/contact/display.py`: pure `CONTACT_FIELDS` (17 fields incl. `service_areas`), `lead_contact_dict`, `group_contact_facts` → (group, label, value) rows for dashboard rendering (groups: Business / Contact / Location / Website & Forms / Social links / Opening hours / Service areas); `src/contact/helpers.py::service_areas_from` normalizes list/raw-JSON/None.
- Search (`src/search/index.py`): `_document_text` sections LOCATION → SERVICES → CONTACT → SOCIAL → OPENING HOURS with `no phone`/`no email` markers; `METADATA_KEYS` (filters) untouched. Summarizer (`src/search/summarizer.py`): business block gains owner/postal code/opening hours/maps/service areas + new top-level `social` dict (`_social_summary`); `context_to_text` renders them.
- Chat (`src/chat/context_builder.py`): `build_lead_block` Contact line gains `owner=`/`postal code=`, plus Address, Social (sanitized), Opening hours, Contact page, Contact form, Maps, Service areas lines — NULLs omitted, under `MAX_BLOCK_CHARS`.
- Opportunities: `OpportunityReport.contact` (input-derived context, never affects scores) — website/phone/email/address/socials + primary contact & best contact method only when a channel exists; `to_llm_text` renders it as a neutral banner; empty for no-website leads (`src/opportunities/aggregator.py`, `base.py`, `report.py`).
- Outreach (`src/outreach/`): deterministic `build_outreach_context` digest (business, location, services, contact, social presence, opening hours, technology, SEO, visual, opportunity summary, reachability) + markdown `outreach_context_text` + `outreach_context_for_lead` loader; never writes email copy.
- Storage: `src/storage/search.py::leads_intelligence` decodes `service_areas_json` → `lead["service_areas"]` (safe `_decode_json`); `leads_intelligence` is the shared contract for all consumers.
- Dashboard (`dashboard.py`): lead detail renders contact via `group_contact_facts` in grouped `####` subsections with link-markdown; opportunity section shows a contact caption (email/phone/website/socials); `_as_dict` includes all 17 contact fields.
- CSV export (`main.py::_export_csv_for_run`): all contact columns exported, `service_areas` joined with `"; "`.
- Verified: full suite 622 tests pass (592 pre-existing + 30 new); `compileall` OK; offline smoke `Run 17` → `exports/leads_20260805_130022.csv` with all 12 contact columns; `import dashboard` OK. Commit `941b318` (pushed).
- AGENTS.md rewritten this session (verified command set, architecture, DB + repo conventions; contact engine now listed among the pure engines).

## Reliability hardening (audit backlog — Phase R1 → R3, 2026-08-26)

A full read-only audit produced `bug.md` (audit backlog: 3 CRITICAL / 12 HIGH / 25 MEDIUM /
~25 LOW, with a recommended fix order). This session executed the first three phases of that
roadmap — the read-only-driven reliability work before any new features. `bug.md` is
now tracked in the repo and is the live source of truth for remaining work.

### Phase R1 — Fetch-path security boundary (commit `e32489d`, `fix(security): add public URL fetch boundary`)
- New shared trust boundary: `src/net/url_guard.py` — `validate_public_http_url` / `is_safe_public_http_url` / `UnsafeUrlError`, injectable DNS resolver.
- Rules: scheme ∈ {http, https}; no embedded credentials; host required; localhost/*.localhost rejected; IP literals must be globally routable (loopback 127/8, RFC1918 10/8 · 172.16/12 · 192.168/16, link-local 169.254/16, unspecified 0/8, multicast, broadcast, CGNAT 100.64/10, docs + IPv6 ::1 / fe80::/10 / fc00::/7 / IPv4-mapped rejected); **DNS check on every resolved address** — a hostname resolving to any private IP is rejected (rebinding defence).
- Seed path (`src/url_loader.py`): unsafe URLs rejected at load; new `SeedRow.url_error` carries a truthful `Invalid/unsafe website URL (…)` reason instead of silently degrading to "no website". IDNs / subdomains / non-default public ports / query strings remain accepted.
- Playwright (`src/scraping/browser_fetch.py`): `fetch()`/`screenshot()` validate pre-`goto`, AND a route-interceptor (`_install_route_guard`) aborts any request (redirect hops, frames, subresources) to a non-public destination — defence-in-depth. Documented residual: theoretical TOCTOU DNS-rebinding window between validation and Chromium's connect (fully closing needs a proxy architecture).
- Enrichment verifier (`src/enrichment/verifier.py`): urllib auto-follow disabled (`_NoRedirectHandler`), redirects followed manually with every hop passing the guard before the next request; cap stays 10; timeout/byte limits unchanged. `verify_candidate` pre-checks so even injected fetchers can't bypass. `_best_verified` (service) also filters unsafe candidates → they can never be accepted or cached FOUND.
- Fixes CRIT-2 (verifier SSRF) + CRIT-3 (seed/Chromium SSRF + local file read). Verified with `tests/test_url_guard.py` (+ enrichment/cache/loader suites). Full suite 935 → 934 pass (1 documented CRM env-failure).

### Phase R2 — Website identity preservation (data-fix `fix(pipeline)`, commit `9ecfb3c`)
- `_process_seed_no_fetch` now preserves `seed.url` in `LeadUpsert`/`ScoringInputs`: a valid seed URL is never demoted to "no website" just because Playwright is missing. Error triage: `url_error` → `"Playwright unavailable; website not fetched"` → `"No website URL provided"` (only for genuinely website-less rows). The `biz://` fallback + no-website behavior are unchanged.
- Dedupe: a URL-bearing seed now gets real URL-normalized identity (no synthetic `biz://` key); `upsert_lead` already preferred `normalize_url_for_dedupe(website_url)` and returns the persisted key — no storage redesign. `--only-failed` re-enters via `website_url IS NOT NULL AND (extraction_success=0 OR last_error IS NOT NULL)` and automatically retries these rows.
- Export (`_export_csv_for_run`): the query now selects `leads.website_url_normalized` and joins derived columns (score/SEO/visual/opportunities/tech) on the persisted identity (legacy `normalize(website_url)` fallback) — fixes H-10 (derived columns no longer strand for no-website leads).
- Fixes CRIT-1 and partially H-10/M-19 (score persistence now works; opportunities/M-18 still R8). New `tests/test_website_identity.py` (CSV/OSM × URL/no-URL, dedupe across runs, derived-score association, `--only-failed` eligibility, export retention). Full suite: 944 → 1 pre-existing env-failure.

### Phase R3 — Upsert contact preservation (fix: `09d5d56`, `fix(storage): preserve existing contact data on upsert`)
- `src/storage/leads.py`: `upsert_lead` now treats empty/whitespace-only strings as missing for all protected text fields (`_normalize_blank_fields` → `_blank_to_none`, covers tabs/newlines SQLite `trim()` misses), and the `ON CONFLICT DO UPDATE` uses `COALESCE`/`NULLIF`/`CASE` — a NULL/empty/whitespace incoming value never erases a stored valid value; valid new data still lands (last-write-wins for valid→valid; phone/email keep `better_contact` rank semantics incl. preserved source/confidence).
- Protected: website_url, business_name, city, state, category, source, osm_id, osm_type, latitude, longitude (plain `COALESCE` — coordinates `0.0` are valid, not missing), address, opening_hours, country, owner_name, postal_code, all social/contact page/form/maps URLs, service_areas (guards `[]`), enrichment_* . **Intentionally not preserved** (per-run state, matches existing replace-* semantics): platform, complexity, load_speed, score, priority, extraction_success, extracted_at, last_error.
- Invariant enforced at the storage boundary (protects every `upsert_lead` caller), not in main.py. Fixes H-5. New `tests/test_upsert_preservation.py` (NULL/empty/whitespace preservation, new-data writes, valid→valid, OSM→crawl, crawl enrichment, zero coordinates, pipeline + export + `leads_intelligence` integration). Full suite: 952 tests.

### Test count
- Currently 98 test files; `python -m unittest discover -s tests` reports **952 tests** (951 pass on any checkout; the single env-dependent `CrmDashboardDataPathTest.test_records_from_editor_df` failure reproduces only when a local `data/lead_crm.xlsx` exists — it reads the real workbook, passes on a fresh checkout).

Remaining nice-to-haves (Phase 10)
- Discovery UX: choose city/category in the dashboard and run it from the UI.
- Harder on OSM results — filter out closed/permanently-closed and low-signal businesses before scrape.
