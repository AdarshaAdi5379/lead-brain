# Lead-Brain Audit Bug Tracker

Source: full audit (code inspection + test suite + live E2E run in /tmp, 2026-08-20). No fixes applied yet — this file tracks them.

Severity legend: CRITICAL (security compromise / major data corruption / fundamental pipeline failure) · HIGH (major functionality incorrect or materially unreliable leads) · MEDIUM (feature works but has meaningful correctness/reliability problems) · LOW (minor / edge case) · INFO (not a bug, useful observation).

---

## CRITICAL

### CRIT-1 — Playwright-less runs destroy `website_url` for every lead — ✅ FIXED (Phase R2)
- **File:** `main.py`
- **Function:** `_async_run` / `_process_seed_no_fetch`
- **Line:** 462–468, 905
- **Root cause:** when `playwright` is unavailable, *every* seed (including seeds with a URL) goes through `_process_seed_no_fetch`, which hardcodes `website_url=None` and `last_error="No website URL provided"`. The upsert then builds a `biz://` key.
- **Impact:** a full CSV run without Playwright stores every lead as website-less; the URL is unrecoverable from the DB. A later Playwright run creates a second row (different dedupe key) → duplicates. `--only-failed` cannot recover them (`WHERE website_url IS NOT NULL`). Enriched leads are hit twice.
- **How to reproduce:** run `python main.py --input business_urls.sample.csv --limit 2` in an env without Playwright; inspect `leads.website_url` — both rows NULL.
- **Recommended fix:** `_process_seed_no_fetch` must preserve `seed.url` when present (and set a truthful `last_error`).
- **Fixed (R2):** `_process_seed_no_fetch` preserves `seed.url` in `LeadUpsert`/`ScoringInputs`; URL-bearing seeds get real URL-normalized identity (no synthetic biz:// key) with truthful `"Playwright unavailable; website not fetched"`. Genuinely website-less seeds keep the unchanged `biz://` fallback and "No website URL provided"; unsafe URLs keep their R1 `Invalid/unsafe website URL …` reason. Regression tests: `tests/test_website_identity.py` (CSV/OSM × URL/no-URL, dedupe across runs, derived-score association, export retention, `--only-failed` retry eligibility).

### CRIT-2 — Enrichment verifier fetches arbitrary URLs with no host validation (SSRF) — ✅ FIXED (Phase R1)
- **File:** `src/enrichment/verifier.py`
- **Function:** `fetch_page`
- **Line:** 50–66
- **Root cause:** `urllib.request.urlopen(request, timeout=timeout_s)` — no scheme/host/IP validation; urllib follows up to 10 redirects across hosts without re-validating. `file://` and internal hosts are not blocked at this layer.
- **Impact:** a DDG result or redirect chain to `127.0.0.1`, `169.254.169.254`, or an internal service is fetched by the pipeline (incl. CI). Bounded (300 KB, HTML content-type gate) but a real SSRF primitive.
- **How to reproduce:** run enrichment with a candidate URL that 302s to `http://127.0.0.1:<port>`; the verifier fetches it.
- **Recommended fix:** validate scheme ∈ {http, https} and reject loopback/private/link-local hosts before and after each redirect.
- **Fixed:** auto-follow disabled (`_NoRedirectHandler`); every hop passes `validate_public_http_url` (`src/net/url_guard.py`) before it is requested; unsafe candidates are also rejected in `_best_verified` so they can never be accepted or cached as FOUND even with injected fetchers. Regression tests: `tests/test_url_guard.py` (DNS/redirect/literal matrix), `tests/test_enrichment_verifier.py::TestRedirectSecurity`, `tests/test_enrichment_service.py::TestUnsafeCandidatesNeverCachedAsFound`.

### CRIT-3 — Seed URLs accept any scheme and internal hosts (SSRF + local file read via Playwright) — ✅ FIXED (Phase R1)
- **File:** `src/url_loader.py`, `src/scraping/browser_fetch.py`
- **Function:** `_clean_url` / `PlaywrightFetcher.fetch`
- **Line:** `url_loader.py:74–80`, `browser_fetch.py:84–96`
- **Root cause:** `_clean_url` only prepends `https://` when no scheme exists; there is no scheme or host rejection anywhere in the fetch path. Chromium happily loads `file:///etc/passwd` and `http://169.254.169.254/`.
- **Impact:** a crafted seed row exfiltrates local files / internal service responses into the DB, search index, and exports. Notably relevant to the weekly GitHub Actions run.
- **How to reproduce:** seed `file:///etc/passwd` (or `http://127.0.0.1:6379`) in the CSV; the pipeline fetches it.
- **Recommended fix:** whitelist http/https schemes and reject loopback/private hosts in `_clean_url` **and** `PlaywrightFetcher.fetch`.
- **Fixed:** shared trust boundary in `src/net/url_guard.py` (scheme whitelist, credential rejection, literal-IP + DNS resolution checks); seed loading rejects unsafe URLs with a truthful `Invalid/unsafe website URL …` reason (`SeedRow.url_error`, never "No website URL provided"); `PlaywrightFetcher.fetch()`/`.screenshot()` validate pre-goto AND route-intercept every request (redirects/frames/subresources) aborting non-public destinations. Known residual: TOCTOU DNS-rebinding window between validation and Chromium's connect (documented; would require proxy architecture). Regression tests: `tests/test_url_guard.py`, `tests/test_url_loader_validation.py::TestSeedUrlTrustBoundary`.


## HIGH

### H-1 — No-website, no-phone, no-email lead scores 60/100 "Warm" and outranks real leads
- **File:** `src/scoring/aggregator.py`, `src/scoring/dimensions.py`
- **Function:** `score_site_lead` / dimension functions
- **Line:** `aggregator.py:63–72`, `dimensions.py:122–124, 274–276, 330–336`
- **Root cause:** six dimensions return 0 with "no signal" notes listed in `AVAILABILITY_NOTES`, so their weight is redistributed onto remaining dimensions; `outreach_potential` then **rewards** the missing website (+30 "Clear improvement opportunity", +20 "Real, active business presence").
- **Impact:** the least valuable lead type (no site, no contact channels) is ranked Warm 60 and passes the default export threshold. Verified by execution and by the E2E run (Phoenicia 60 Warm > Quack's 34, example.com 35).
- **How to reproduce:** score a seed with only name/category/city/source → 60 Warm; same row with website+phone+email → 55.
- **Recommended fix:** when no website and no contact channels exist, cap outreach/redistribution (treat missing-website dimensions as penalized, not inapplicable).

### H-2 — Legacy "+40 no website" rule → 90 "Hot" and export recommendation "Contact immediately"
- **File:** `src/scoring/legacy.py`, `main.py`
- **Function:** `score_lead` / `_fallback_lead_score` / `_export_csv_for_run`
- **Line:** `legacy.py:53–64`, `main.py:631–634, 1245–1255`
- **Root cause:** `score_lead` adds +40 for missing website (and +15/+15 for missing phone/email) — the inverse of modern scoring. It fires in the fallback path and at export time for rows whose score-row merge failed (all biz:// leads).
- **Impact:** E2E export shows both no-website leads with `recommendation: "Contact immediately. Top signals: No website URL found (+40)."` — contacting a lead with zero contact channels.
- **Recommended fix:** remove the +40/+15/+15 adjustments from `legacy.py` or stop using `score_lead` at export.

### H-3 — `extraction_success` is model-reported, and run stats mislabel failures as success
- **File:** `src/extraction_schema.py`, `main.py`
- **Function:** `validate_extracted_lead` / `_async_run`
- **Line:** `extraction_schema.py:49–57,102`, `main.py:466–467, 684, 715–718, 796–798`
- **Root cause:** `extraction_success` is the LLM's self-reported boolean (default False when absent), forced False on exceptions; `RunStats.successful_extractions = ok` counts *successful upserts*, not extractions; `failed` counts only upsert exceptions.
- **Impact:** E2E run reported "Finished URLs=6 ok=6 failed=0" while 3 of 6 leads had failed/no extraction. Dashboard/CI stats systematically misleading. Semantics = "LLM succeeded", not "everything succeeded".
- **Recommended fix:** count real extraction outcomes in stats; rename or document the metric.

### H-4 — CRM page crashes with `NameError` — dashboard CRM tab unusable
- **File:** `dashboard.py`
- **Function:** `_crm_filter_rows`
- **Line:** 1357–1368
- **Root cause:** nested `_in()` references `row`, which exists only inside the list-comprehension scope.
- **Impact:** `_crm_filter_rows` is called unconditionally on the CRM page; any render with workbook rows raises `NameError: name 'row' is not defined`. Untested code path.
- **How to reproduce:** open the dashboard CRM tab with rows in the workbook.
- **Recommended fix:** pass `row` into `_in(row, column, options)`.

### H-5 — Re-runs clobber stored contact columns with NULLs (only phone/email protected) — ✅ FIXED (Phase R3)
- **File:** `src/storage/leads.py`
- **Function:** `upsert_lead`
- **Line:** 159–204
- **Root cause:** `ON CONFLICT DO UPDATE` overwrites address, owner_name, social URLs, opening_hours, postal_code, service_areas, lat/lon etc. with `excluded.*` unconditionally; only phone/email use `better_contact`, and only the 5 `enrichment_*` columns use `COALESCE`.
- **Impact:** a weaker re-run (failed crawl → empty signals) NULLs out previously stored deterministic contact data — "valid value → NULL overwrite".
- **Recommended fix:** apply `COALESCE(excluded.x, leads.x)` per column (or per-field preservation checks).
- **Fixed (R3):** `upsert_lead` now normalizes empty/whitespace-only protected text fields to `None`, and the `ON CONFLICT DO UPDATE` uses `COALESCE`/`NULLIF` for contact/identity/enrichment columns — a NULL/empty/whitespace incoming value never erases a stored valid value, while valid new data still lands (last-write-wins for valid→valid; phone/email keep `better_contact`; `service_areas_json` guards `[]`/`""`). Intentionally not preserved per-run state columns (score/priority/platform/complexity/load_speed/extraction_success/last_error) match existing replace-* semantics. Regression tests: `tests/test_upsert_preservation.py` (NULL/empty/whitespace preservation, new-data writes, valid→valid, OSM→crawl, crawl enrichment, zero-coordinate handling, pipeline+export+dashboard integration).

### H-6 — Scoring reads the LLM's raw phone/email, not the stored deterministic winner
- **File:** `main.py`, `src/scoring/dimensions.py`
- **Function:** `_run_seeds` / `_phone`/`_email`
- **Line:** `main.py:599–624` vs `main.py:654–665`, `dimensions.py:39–44, 87–92`
- **Root cause:** `ScoringInputs` is built from `extracted` (LLM payload) 30 lines *before* `pick_across_sources` merges deterministic contact data; dimensions read `extracted.get("phone"/"email")`.
- **Impact:** a lead whose only phone comes from JSON-LD (rank 100) is scored contactability 0 while the DB stores the phone; on LLM failure the stored row has a valid deterministic phone but the score says "no contact channels".
- **Recommended fix:** run the contact merge before scoring and feed the winner into `ScoringInputs`.

### H-7 — False-positive phones: ZIP codes and arbitrary digit runs stored as phones (verified live)
- **File:** `src/contact/recovery.py`, `src/llm_extraction.py`
- **Function:** `_plausible_phone` / `_sanitize_phone`
- **Line:** `recovery.py:26,35–40`, `llm_extraction.py:386–401`
- **Root cause:** `PHONE_TOKEN_RE` matches any 7–18 char digit-dot-dash-space token; plausibility = 7–15 digits + not a date. Only pure IPv4 is rejected.
- **Impact:** E2E: Master Donuts stored `phone = "78741 512 215 2696"` (ZIP+phone, `visible_text` rank 70) which **beat the correct OSM phone `+1-512-215-2696` (rank 40)**. Exported, displayed, indexed, used in outreach.
- **Recommended fix:** tighten the token regex (require area-code-like structure), reject tokens starting with a 5-digit ZIP run, require separation from address context.

### H-8 — Empty/placeholder pages certified "Excellent" 98–100/100 (verified live ×3)
- **File:** `src/visual/score.py`, `src/visual/signals.py`, `src/visual/capture.py`
- **Function:** `score_page` / signal helpers
- **Line:** `score.py:65–75`, `signals.py:125–126, 271–282, 314`, `capture.py:186–200`
- **Root cause:** page score starts at 100; the "no CTA" penalty (-8) is skipped when probe `cta_count` is absent (reused screenshots / `{}` probes); `STRONG_BRAND` fires on a 99%-white page; mobile gains a responsive bonus with no overflow probe.
- **Impact:** E2E: example.com 98/100, example.org 98/100, real Squarespace bakery 100/100 whose own summary says "Page appears sparse". Inflates `visual_presentation`, suppresses the redesign opportunity.
- **Recommended fix:** start from a neutral baseline, penalize missing probes, require ≥1 actual content/CTA signal for "Excellent".

### H-9 — Enrichment can accept a wrong website (weak brand-scoring paths)
- **File:** `src/enrichment/match.py`
- **Function:** `score_candidate`
- **Line:** 74–81
- **Root cause:** partial-brand awards 0.30 for ≥50% token containment (0.30+0.35 phone+0.15 location = 0.80 ≥ 0.75 acceptance); single-token names get 0.55 for any page containing the word in title+body (+0.35 phone = 0.90). Phone evidence is a raw digit substring test.
- **Impact:** a directory/competitor page ("Plumbing Services | Austin" containing ≥50% of "Austin Plumbing Co") or any page mentioning a single-token name can be accepted as the business's official website.
- **Recommended fix:** require full-name sequence, exact normalized phone, or email-domain evidence for acceptance; gate single-token names.

### H-10 — CSV export silently drops ALL derived columns for no-website leads (verified live) — ✅ FIXED (Phase R2)
- **File:** `main.py`
- **Function:** `_export_csv_for_run`
- **Line:** 1210–1211, 1299–1300
- **Root cause:** the export join key is `normalize_url_for_dedupe(record["website_url"])` — `""` for every no-website lead — which never matches a stored `biz://` key, so the tech/SEO/score/opportunity/visual merges are skipped.
- **Impact:** E2E export: Phoenicia and Shipley rows have `final_score`, `priority_label`, `contactability_score`, `opportunity_count`, `visual_score`, `site_seo_score` all empty, even though `lead_scores` has 6 rows in the DB.
- **Recommended fix:** key the merge map on the stored `website_url_normalized` (select it in the export query).
- **Fixed (R2):** the export query selects `leads.website_url_normalized` and joins derived intelligence on the persisted key (`normalize_url_for_dedupe(website_url)` remains only as a legacy-row fallback), so biz://-keyed and URL-keyed rows both keep every derived column. Note: the separate legacy `+40`/recommendation overwrite belongs to H-2 and stays open. Test: `tests/test_website_identity.py::TestExportRetainsWebsiteAndDerivedColumns`.

### H-11 — SEO audit scores a well-formed real site 0/100 "Critical" (verified live)
- **File:** `src/seo/site_audit.py`, `main.py`
- **Function:** `audit_site` / `_audit_site_for_seed`
- **Line:** `site_audit.py:257–284`, `main.py:853–869`
- **Root cause:** missing-page penalties (`no_contact_page` −10, `no_about_page` −5, `no_services_page` −5, `no_sitemap` −5, `no_robots` −5) fire whenever a page *type* isn't among crawled pages; the crawler's own contact page (`/new-page`, detected by the contact engine) is classified `page_type="other"` by the SEO audit. Combined with per-page deductions, 4 well-formed pages → site_score 0.
- **Impact:** outreach copy ("SEO 0/100"), opportunities, and search ranking repeat a demonstrably wrong number for decent sites.
- **Recommended fix:** only penalize absent page types when the crawl was complete; align page-type classification with the crawler.

### H-12 — Platform override can contradict stored detections (WordPress 85 + platform=shopify)
- **File:** `main.py`, `src/fingerprinting/base.py`
- **Function:** `_platform_override`
- **Line:** `main.py:830–840, 594–595, 721–728`, `base.py:41–47`
- **Root cause:** `_platform_override` picks the single highest-confidence mapped detection (≥60) and overwrites `extracted["platform"]` with no contradiction check; all detections (including the losing CMS) are persisted as-is. Hybrid sites produce contradictory rows.
- **Impact:** internally inconsistent lead records (`platform=shopify` + WordPress/WooCommerce detections) flow to scoring, export, search, chat.
- **Recommended fix:** reconcile (trust CMS-category detection over e-commerce when both fire, or drop the override).

---

## MEDIUM

### M-1 — CSV formula injection (`=`,`+`,`-`,`@` cells written raw)
- **File:** `main.py` / `dashboard.py`
- **Function:** `_export_csv_for_run` / `_write_csv`
- **Line:** `main.py:1234–1244`, `dashboard.py:1053–1067`
- **Impact:** opening exports in Excel/Sheets evaluates formulas from crawled data.
- **Fix:** prefix dangerous leading characters with `'` in a writer wrapper used by both paths.

### M-2 — `better_contact` tie never upgrades: corrected CSV phone/email never replaces stale stored value
- **File:** `src/contact/sources.py`
- **Function:** `pick_across_sources`
- **Line:** 127–135
- **Impact:** a user who fixes `business_urls.csv` and re-runs finds the old value retained forever.
- **Fix:** allow equal-rank upgrade when incoming differs from stored (or add explicit precedence).

### M-3 — JSON-LD `Person` nodes leak owner_name/phone/email at rank 100
- **File:** `src/contact/jsonld.py`
- **Line:** 12–34, 135–136, 244–246, 288–301
- **Impact:** blog author / review author / employee Person blocks supply business contact facts that outrank everything, including the real CSV data.
- **Fix:** exclude `Person`-typed nodes from business contact harvest (or gate behind organization context).

### M-4 — JSON-LD string-form `address` silently discarded (only dict accepted)
- **File:** `src/contact/jsonld.py`
- **Function:** `_extract_address`
- **Line:** 182–185
- **Impact:** the common `"address": "123 Main St, Springfield, IL 62701"` string form is dropped entirely.
- **Fix:** parse the string form (or at least keep it as `address`).

### M-5 — `openingHours` array stored as Python list repr
- **File:** `src/contact/jsonld.py`
- **Line:** 155–158
- **Impact:** dashboard/CSV/search show `['Mo-Fr 09:00-17:00']` instead of readable hours.
- **Fix:** join list values with "; ".

### M-6 — Malformed/scheme-less social URLs stored (self-referential `site.com/facebook.com/page`)
- **File:** `src/contact/extractor.py`, `src/contact/social.py`
- **Line:** `extractor.py:45–51`, `social.py:95–101`
- **Impact:** broken/self-referential URLs land in `facebook_url`/… columns, exported, indexed.
- **Fix:** drop (don't store) URLs that fail normalization; resolve scheme-less hrefs against the site root host only.

### M-7 — Enrichment migration IntegrityError silently swallowed → stale biz:// row + duplicate later
- **File:** `src/storage/enrichment.py`, `src/enrichment/service.py`
- **Line:** `enrichment.py:101–125`, `service.py:239–242`
- **Impact:** migration silently aborted mid-loop, partial state, `connection.commit()` never runs; later upsert creates a URL-keyed row → duplicate.
- **Fix:** single-row migration (LIMIT 1) + `INSERT ... ON CONFLICT` or catch IntegrityError per row.

### M-8 — Duplicate leads across `biz://` vs URL-keyed paths (no-website run, then enriched run, never merges)
- **File:** `src/storage/leads.py`, `src/storage/enrichment.py`
- **Line:** `leads.py:243–259`, `enrichment.py:83–99`
- **Impact:** same business enters twice; unique index can't catch it (different keys).
- **Fix:** resolve/merge `biz://`-keyed rows by normalized URL before upsert in every pipeline path.

### M-9 — Stale `biz://` row persists when the URL-keyed row already exists
- **File:** `src/storage/enrichment.py`
- **Line:** 83–99
- **Impact:** two lead rows for the same business persist (dashboard, CRM workbook, exports).
- **Fix:** when the URL row exists, also migrate/delete the matching biz row (or merge contacts).

### M-10 — Dashboard notes/outreach_sent edits silently reverted by next Excel sync
- **File:** `dashboard.py`, `src/crm/sync.py`
- **Line:** `dashboard.py:1126–1152`, `sync.py:94`
- **Impact:** the dashboard edit is lost/diverged on the next CRM sync + save.
- **Fix:** route dashboard notes edits through the merge-aware write (update the workbook too), or make SQLite win for notes.

### M-11 — Crawler call not exception-wrapped; no-fetch scoring unguarded — one crawler exception aborts the whole batch
- **File:** `main.py`
- **Line:** 506, 887–900
- **Impact:** contradicts the AGENTS.md guarantee that "a failure never breaks the run".
- **Fix:** wrap crawl + no-fetch scoring in try/except with degrade-to-homepage / failed-seed handling.

### M-12 — Enrichment redirect mis-attribution: stores pre-redirect URL, verifies post-redirect
- **File:** `src/enrichment/service.py`, `verifier.py`
- **Line:** `service.py:103`, `verifier.py:58`
- **Impact:** a redirector/shortener domain is stored as the business website.
- **Fix:** store the post-redirect final URL or reject candidates whose final host differs.

### M-13 — OSM `website` tag / CSV URLs not filtered for social/directory hosts
- **File:** `src/discovery/osm.py`, `src/url_loader.py`
- **Line:** `osm.py:170`, `url_loader.py:74–80`
- **Impact:** a lead whose OSM `website` tag is a Facebook/Yelp page gets crawled and stored as `website_url`.
- **Fix:** route OSM/CSV website values through the same social/directory host rejection used by enrichment.

### M-14 — Crawler lowercases URL paths → 404s on case-sensitive servers
- **File:** `src/scraping/link_extractor.py`, `focused_crawler.py`
- **Line:** `link_extractor.py:64–74`, `focused_crawler.py:195`
- **Impact:** `/About-Us` fetched as `/about-us`, ranked pages silently skipped.
- **Fix:** preserve path case in `normalize_page_url` (dedupe key ≠ fetch URL).

### M-15 — "Top negative reasons" contains positive reasons (marker check dead)
- **File:** `src/scoring/aggregator.py`
- **Function:** `_split_reasons`
- **Line:** 117–139
- **Root cause:** `"(+)" in reason` never matches `"(+10)"` strings; positivity determined solely by `score >= 35`, so dimensions scoring < 35 contribute their "+N" reasons to the negative list (e.g. "Street address present (+10)", "Website present (+15)"). Verified in E2E DB.
- **Fix:** use a regex like `r"\(\+\d"` for the marker check.

### M-16 — LLM outreach drafts can invent findings; validation doesn't check numbers
- **File:** `src/outreach/generator.py`, `src/outreach/validation.py`, `src/outreach/context.py`
- **Line:** `generator.py:386–419`, `validation.py:54–103`, `context.py:224–290`
- **Impact:** a model can write "your site loads slowly", a wrong phone, or a fake score into an unsolicited email and pass all checks.
- **Fix:** include the deterministic issue facts in the fenced block; validate numbers/scores; require ≥1 fact label match.

### M-17 — Outreach template claims "I took a close look at the website" even when no crawl/audit ran
- **File:** `src/outreach/templates.py`, `src/outreach/generator.py`
- **Line:** `templates.py:55–56, 246–251`, `generator.py:362–383`
- **Impact:** emails can state a review happened when none did.
- **Fix:** gate the "close look" copy on actual crawl/audit state.

### M-18 — No-website leads get zero opportunities (funnel-fix detector never fires)
- **File:** `src/opportunities/aggregator.py`
- **Line:** 25–26
- **Impact:** the detector most relevant to no-phone/no-email/no-site leads never runs for them (verified: 0 rows for the no-website E2E lead).
- **Fix:** allow contact-funnel detection for no-website leads (only skip website-dependent detectors).

### M-19 — Engine outputs for no-website leads never persisted — ✅ FIXED (Phase R2, score persistence)
- **File:** `main.py`
- **Line:** 721–768
- **Root cause:** `normalized = normalize_url_for_dedupe(seed.url) if seed.url else ""` → `get_lead_id_by_url("")` → None → persistence skipped.
- **Fix:** resolve lead id by the actual dedupe key returned by `upsert_lead`.
- **Fixed (R2):** with seed URLs preserved, the no-fetch path now resolves `lead_id` via upsert's returned key for BOTH identity kinds and persists the deterministic score. Remaining for R8: opportunity/funnel detection itself still does not run on the no-fetch path (M-18). Tests: `tests/test_website_identity.py::TestDerivedDataStaysAssociated`, `TestWebsiteIdentityPreservation`.

### M-20 — Costing preset bug: `gpt-4.1-mini`/`gpt-4.1-nano` priced as `gpt-4.1`
- **File:** `src/costing.py`
- **Line:** 119–132
- **Impact:** 5×/20× cost overestimate; breaks `--max-cost-usd` early-stop accuracy for those models.
- **Fix:** order checks most-specific-first (mini/nano before 4.1).

---

## LOW

- **L-1** — Social skip-path matching case-sensitive (facebook.com/Help stored) + substring over-rejection — `src/contact/social.py:60–62`
- **L-2** — Duplicate social URLs (http/https variants); no TikTok/Pinterest columns — `social.py:103–104, 11–18`
- **L-3** — 429/401: no retry (correct) but no run-level backoff/circuit breaker → remaining run fails fast — `openai_responses.py:49`, `llm_extraction.py:165–167`
- **L-4** — Chat prompt-injection fence: `</lead_data>` in crawled text closes fence early — `src/chat/safety.py:25–35`
- **L-5** — Chat grounding check accepts any digit ("phone is 555-0123" passes) — `safety.py:85–90`
- **L-6** — Search `offset` validated but never applied (pagination returns duplicates) — `src/search/search_service.py:153, 179–182`
- **L-7** — Absence-of-evidence negative claims ("no contact form", "no social links") from bounded crawl — `generator.py:152–167`, `context.py:183–184`, `search/index.py:133–136`
- **L-8** — Search metadata `lead_score` reads legacy `leads.score`; card reads `lead_scores.final_score` — `src/search/index.py:248`
- **L-9** — SEO banner/CSV miscount titles for text-only pages — `src/seo/report.py:33, 91, 119`
- **L-10** — Text-only cached pages scored 100 and inflate the site average — `page_audit.py:89`, `site_audit.py:174`
- **L-11** — OSM/CSV phone/email stored byte-for-byte (no sanitization) on no-fetch path — `main.py:907–908`, `osm.py:171–172`
- **L-12** — Discovery in-run dedupe key omits state — `src/discovery/discovery.py:70–81`
- **L-13** — No-website leads: no opportunities at all (see M-18) — `aggregator.py:25–26`
- **L-14** — `OpportunityReport.contact` dead; opportunities `to_llm_text` has no callers — `aggregator.py:28,43`, `report.py:20`
- **L-15** — `_process_seed_no_fetch` / no-fetch loop not exception-guarded (see M-11) — `main.py:464–468`
- **L-16** — Seed CSV phone/email bypass sanitization (only LLM/JSON-LD values sanitized) — `main.py:659, 664, 907–908`
- **L-17** — Verifier content-type accepts `xml` as verification — `verifier.py:58–64`
- **L-18** — Enrichment `checked_at=0` / mixed datetime formats — `service.py:204, 29`
- **L-19** — `visual_presentation_score` missing from export columns — `main.py:78–150`
- **L-20** — `--only-failed` reconstructs seeds without phone/email/address/osm data — `main.py:1363–1391`
- **L-21** — Enrichment LOW_CONFIDENCE candidate URL only survives as text in `last_error` — `service.py:110`
- **L-22** — `None/100` rendered if visual/seo columns NULL — `dashboard.py:850, 918`
- **L-23** — No robots.txt respect by crawler (only audit signal, off by default) — `focused_crawler.py`
- **L-24** — `full_page` visual evidence field hardcoded None — `visual/report.py:77`
- **L-25** — CRM manual cell can never be blanked (empty = no-op on sync) — `sync.py:94`, `leads.py:367`

---

## INFO (verified, no action required)

- Schema/migrations consistent: all 34 additive columns present in SCHEMA_SQL (checked programmatically); `test_db_migrations.py` covers a pre-Phase-9 DB.
- Upsert commits per call; dedupe key + unique index on `website_url_normalized` correct; NULL-website leads merge on identical biz:// identity.
- Enrichment cache correct: FOUND/NOT_FOUND/LOW_CONFIDENCE cached, failures never cached, TTL 30d enforced, key = sha1(name|city|state|category).
- No hardcoded secrets; `.env`/`data/`/`exports/` gitignored; SQL fully parameterized; no subprocess/eval/pickle; error logging redacts headers.
- `phone_confidence`/`email_confidence` always NULL (confidence tiebreak never fires).
- Per-lead `replace_*` delete-then-insert: no duplicates, but old-run history silently lost on re-run (documented behavior).
- `SEO_BLEND_WEIGHT`, `visual_redesign_max`, `ScoringInputs.last_error` unused on the main path.
- LLM failure does NOT erase deterministic contact data (verified).
- 898/898 tests pass on a fresh checkout; 1 documented env-dependent failure (`CrmDashboardDataPathTest.test_records_from_editor_df`) reproduces only when `data/lead_crm.xlsx` exists (reads real workbook; root cause: `CrmService` defaults workbook path to `DATA_DIR/lead_crm.xlsx` regardless of DB — also causes cross-DB contamination).

---

## Dead code / unused data (do not delete without review)

- Never called: `discovery._seed_key`, `discover_leads`, `DiscoveredLead`, `export_discovery_csv`; `nominatim.reverse_geocode` (tests only); `enrichment.verify_candidate`; `page_cache.get_hash`; `ContactSignals.non_empty_fields`; `recovery.iter_candidates`; `ChatService.summarize_lead`/`retrieve_context`; `ConversationMemory.latest_lead_ids` (tests); `embeddings_for_run` (tests); `validate_text_safety` (tests); `SearchService.update_lead` (tests); `EmbeddingCache.get`; `opportunities.to_llm_text`; fingerprint `probe_paths`; `_BAND_RE`; `total_db_leads` (dashboard).
- Written, never read: `phone_confidence`/`email_confidence`; `CostEstimate.total_tokens`; `WellKnownProbe.robots_url/sitemap_url`; `ScoringConfig.visual_redesign_max`; `ScoringInputs.last_error`; `SEO_BLEND_WEIGHT` (legacy fallback only); `osm_type`; `VisualPageReport.evidence["full_page"]`; `canonical` signal kind / `css_urls`; `CrawlMetadata`; legacy export `recommendation` computation (overwritten); `_build_contact_fields` `extracted` param.
- Unused imports in 8 files (hygiene).

---

## Recommended fix order

1. **CRIT-1** — preserve `website_url` in the no-Playwright path
2. **H-4** — CRM `NameError` (one-line fix)
3. **H-10 + H-2** — export join by `website_url_normalized`; delete legacy +40/recommendation logic
4. **H-1 + H-6** — scoring: cap no-site redistribution; feed deterministic contact winner into scoring
5. **H-7** — phone false positives (regex/ZIP guard)
6. **CRIT-2 + CRIT-3** — scheme/host/IP validation in enrichment verifier and seed/fetcher paths
7. **H-5** — COALESCE-style preservation for all contact columns in `upsert_lead`
8. **H-8** — visual score baseline/probe handling
9. **H-9 + M-12** — enrichment acceptance hardening
10. **H-11** — SEO page-type alignment + under-crawl penalty gating
11. **H-3** — truthful `extraction_success`/run stats
12. **H-12** — platform/detection reconciliation
13. **M-16/M-17** — outreach LLM grounding
14. **M-1** — CSV formula-injection escaping
15. **M-15** — reason marker regex fix
16. **M-7/M-8/M-9** — dedup/migration hardening
17. **M-3/M-4/M-5** — contact JSON-LD fixes
18. Remaining MEDIUM/LOW backlog