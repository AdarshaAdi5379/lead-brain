Storage notes (v1)

- SQLite file: `data/leads.sqlite`
- Tables created by: `python -m src.storage.init_db`
- Dedupe key: `leads.website_url_normalized` (UNIQUE)
- Init/migrate: `python -m src.storage.init_db` (schema in `src/storage/db.py`)

Tables by feature
- Leads + runs: `scraping_runs`, `leads` (`website_url_normalized` UNIQUE; contact columns via additive migration — owner_name, address, postal_code, country, opening_hours, social_urls JSON, contact page/form URLs, google_maps_url, service_areas JSON)
- Scraping/detection: `technology_detections`
- SEO audit: `seo_audits`, `seo_page_audits`
- Visual audit: `visual_audits` (per-lead, `lead_id` UNIQUE), `visual_page_audits` (per-page, FK → `visual_audits.id` ON DELETE CASCADE) — additive `llm_summary` column; persistence in `src/storage/visual.py` (`replace_visual_audit`, `audits_by_lead`, `page_audits_for_audit`, `audits_for_run`)
- Scoring: `lead_scores`
- Opportunities: `business_opportunities`
- Semantic search: `lead_embeddings` (incremental index per lead; storage/decode in `src/storage/search.py` — `leads_intelligence` decodes JSON columns incl. `service_areas`)
- Chat: `chat_sessions`, `chat_messages` (opt-in persistence, `CHAT_PERSIST_SESSIONS`; `src/storage/chat.py`)


