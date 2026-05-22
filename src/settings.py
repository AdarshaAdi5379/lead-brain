from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
DB_PATH = DATA_DIR / "leads.sqlite"

# Google Places API (Phase 8 — Lead Discovery)
GOOGLE_MAPS_API_KEY: Optional[str] = os.environ.get("GOOGLE_MAPS_API_KEY", "").strip() or None
PLACES_TEXT_SEARCH_RADIUS: int = int(os.environ.get("GOOGLE_PLACES_TEXT_SEARCH_RADIUS", "50000"))
PLACES_LANGUAGE: str = os.environ.get("GOOGLE_PLACES_LANGUAGE", "en")

