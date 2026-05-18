#!/usr/bin/env bash
set -euo pipefail

# Example weekly runner (v1).
# Usage:
#   ./scripts/run_weekly.sh business_urls.csv
#
# Recommended: run via cron weekly.

INPUT_CSV="${1:-}"
if [[ -z "${INPUT_CSV}" ]]; then
  echo "Usage: $0 <business_urls.csv>" >&2
  exit 2
fi

python -m src.storage.init_db
python main.py --input "${INPUT_CSV}" --limit 200 --min-score-export 30

