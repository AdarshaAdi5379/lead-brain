# Second Brain Lead Finder (v1)

Manual CSV → scrape (Playwright) → LLM extract → score → SQLite → CSV exports → Streamlit dashboard.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m playwright install --with-deps chromium
```

Create a `.env` file:

```bash
OPENAI_API_KEY=...

# Optional (only required if you use --max-cost-usd)
OPENAI_INPUT_COST_PER_1K=0.0
OPENAI_OUTPUT_COST_PER_1K=0.0
```

Seed CSV format:
- `business_name,category,url,city,state`
- See `business_urls.sample.csv`.

## Run pipeline

```bash
python -m src.storage.init_db
python main.py --input business_urls.csv --limit 200 --min-score-export 30
```

Re-run failed leads already in the DB:

```bash
python main.py --input business_urls.csv --only-failed --limit 200
```

Cost stop (optional):

```bash
export OPENAI_INPUT_COST_PER_1K=0.0
export OPENAI_OUTPUT_COST_PER_1K=0.0
python main.py --input business_urls.csv --max-cost-usd 5
```

## Dashboard

```bash
streamlit run dashboard.py
```

## Discovery mode (Google Places API)

Discover leads automatically without a seed CSV:

```bash
# Inline: single query
python main.py --discover --category plumber --location "Austin, TX" --limit 50

# Batch: CSV of queries (columns: category, location)
python main.py --discover --discover-queries queries.csv --limit 200
```

Set `GOOGLE_MAPS_API_KEY` in `.env` (get a key from Google Cloud Console).

## Tests

```bash
python -m unittest discover -s tests
```
