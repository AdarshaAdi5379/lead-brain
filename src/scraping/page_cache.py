from __future__ import annotations

import hashlib
import json
import threading
from pathlib import Path
from typing import Any, Optional


def content_hash(text: str) -> str:
    """Stable sha256 of cleaned text, used to detect page changes over time."""
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


class PageCache:
    """Small page store for the focused crawler.

    - In-memory dict avoids re-fetching the same URL twice within a run.
    - Auto-persists to disk so unchanged pages can be reused by later runs
      (a later incremental recrawl can skip fetching/LLM-sending a page whose
      content hash has not changed).
    """

    def __init__(self, cache_dir: Path, cache_file: str = "pages.json") -> None:
        self._dir = Path(cache_dir)
        self._file = self._dir / cache_file
        self._memory: dict[str, dict[str, Any]] = {}
        self._loaded = False
        self._lock = threading.Lock()

    def _load(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        if not self._file.exists():
            return
        try:
            with self._file.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
            self._memory = data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            self._memory = {}

    def _save(self) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)
        tmp = self._file.with_suffix(".tmp")
        try:
            with tmp.open("w", encoding="utf-8") as handle:
                json.dump(self._memory, handle, ensure_ascii=False)
            tmp.replace(self._file)
        except OSError:
            pass

    def get(self, url: str) -> Optional[str]:
        """Return the cleaned text cached for a URL, or None on a miss."""
        if not url:
            return None
        with self._lock:
            self._load()
            record = self._memory.get(url)
        if not isinstance(record, dict):
            return None
        text = record.get("text")
        return text if isinstance(text, str) else None

    def get_html(self, url: str) -> Optional[str]:
        """Return the bounded HTML fragment cached for a URL, or None on a miss.

        Legacy records (written before HTML was stored) return None so callers
        can fall back to text-only signals instead of treating the page as
        having missing HTML."""
        if not url:
            return None
        with self._lock:
            self._load()
            record = self._memory.get(url)
        if not isinstance(record, dict):
            return None
        html = record.get("html")
        return html if isinstance(html, str) and html else None

    def get_hash(self, url: str) -> Optional[str]:
        if not url:
            return None
        with self._lock:
            self._load()
            record = self._memory.get(url)
        if not isinstance(record, dict):
            return None
        value = record.get("hash")
        return value if isinstance(value, str) else None

    def put(self, url: str, text: str, html: Optional[str] = None) -> None:
        if not url:
            return
        text = text or ""
        record = {"hash": content_hash(text), "text": text}
        if html:
            record["html"] = html
        with self._lock:
            self._load()
            self._memory[url] = record
            self._save()

    def status(self) -> dict[str, int]:
        with self._lock:
            self._load()
            from_disk = self._memory
            return {"entries": len(from_disk)}

    def clear(self) -> int:
        with self._lock:
            self._loaded = True
            count = len(self._memory)
            self._memory = {}
            try:
                self._file.unlink(missing_ok=True)
            except OSError:
                pass
            return count