"""Shared synthetic fixtures for website enrichment tests (no network)."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from src.storage.db import init_db


@dataclass(frozen=True)
class FakePage:
    ok: bool
    title: str = ""
    text: str = ""
    error: Optional[str] = None
    url: str = ""


def html_page(title: str, body: str) -> FakePage:
    return FakePage(
        ok=True,
        title=title,
        text=body,
    )


def failing_page(error: str = "connection refused") -> FakePage:
    return FakePage(ok=False, error=error)


def lead(name: str = "Radiant Plumbing", **overrides) -> dict:
    """A realistic website-less OSM-style lead (as a plain dict)."""
    base = {
        "business_name": name,
        "category": "plumber",
        "city": "Austin",
        "state": "TX",
        "country": "US",
        "phone": "(512) 555-0123",
        "email": None,
        "address": "123 Main St",
        "postal_code": "78701",
        "latitude": 30.27,
        "longitude": -97.74,
        "source": "openstreetmap",
    }
    base.update(overrides)
    return base


def matching_page(name: str = "Radiant Plumbing") -> FakePage:
    return html_page(
        title=f"{name} Austin TX | Plumbing & Drains",
        body=(
            f"{name} serves the greater Austin Texas area. Call (512) 555-0123 "
            "for plumbing, drain cleaning and repiping. Licensed plumber."
        ),
    )


DDG_RESULTS_HTML = """
<html><body>
<a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fradiantplumbing.com%2F">Radiant Plumbing</a>
<a class="result__a" href="https://radiantplumbing.com/contact">Contact</a>
<a class="result__a" href="https://www.yelp.com/biz/radiant-plumbing-austin">Yelp</a>
<a class="result__a" href="https://www.facebook.com/radiantplumbing">Facebook</a>
<a class="result__a" href="https://radiantplumbing.com/?utm_source=ddg&amp;ref=ad">Home</a>
</body></html>
"""


class EnrichmentSqliteFixture(unittest.TestCase):
    """Temp SQLite db with the real schema, cleaned up automatically."""

    def setUp(self) -> None:
        self._tmp = tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False)
        self.tmp_path = Path(self._tmp.name)
        self._tmp.close()
        self.connection = sqlite3.connect(self.tmp_path)
        self.connection.row_factory = sqlite3.Row
        init_db(self.connection)

    def tearDown(self) -> None:
        self.connection.close()
        self.tmp_path.unlink(missing_ok=True)


def seed(**overrides) -> object:
    """SeedRow builder with website-less defaults."""
    from src.url_loader import SeedRow

    base = {
        "business_name": "Radiant Plumbing",
        "category": "plumber",
        "url": None,
        "city": "Austin",
        "state": "TX",
        "phone": "(512) 555-0123",
        "source": "openstreetmap",
    }
    base.update(overrides)
    return SeedRow(**base)


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")