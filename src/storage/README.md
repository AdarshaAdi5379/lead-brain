Storage notes (v1)

- SQLite file: `data/leads.sqlite`
- Tables created by: `python -m src.storage.init_db`
- Dedupe key: `leads.website_url_normalized` (UNIQUE)
- Init/migrate: `python -m src.storage.init_db` (schema in `src/storage/db.py`)

Tables by feature
- Leads + runs: `scraping_runs`, `leads` (`website_url_normalized` UNIQUE)
- Scraping/detection: `technology_detections`
- SEO audit: `seo_audits`, `seo_page_audits`
- Visual audit: `visual_audits` (per-lead, `lead_id` UNIQUE), `visual_page_audits` (per-page, FK → `visual_audits.id` ON DELETE CASCADE) — additive `llm_summary` column; persistence in `src/storage/visual.py` (`replace_visual_audit`, `audits_by_lead`, `page_audits_for_audit`, `audits_for_run`)
- Scoring: `lead_scores`
- Opportunities: `business_opportunities`


