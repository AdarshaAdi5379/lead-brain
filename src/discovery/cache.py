from __future__ import annotations

import json
import shutil
import time
import zlib
from pathlib import Path
from typing import Any, Callable, Optional

from src.settings import DISCOVERY_CACHE_DIR


def clear_discovery_cache(directory: Path = DISCOVERY_CACHE_DIR) -> int:
    """Wipe every local discovery cache entry (geocoding + POI responses)."""
    return DiskCache(directory, ttl_hours=0.0).clear()


class DiskCache:
    """Tiny TTL JSON cache on disk.

    Keys are arbitrary strings (callers should hash requests, see
    ``src.discovery._http.cache_key``). Values are stored gzip-compressed to
    keep ``data/cache/`` tidy. On any read/format error the entry is treated
    as a miss, so corruption never breaks a run.
    """

    def __init__(self, directory: Path, *, ttl_hours: float) -> None:
        self._directory = Path(directory)
        self._ttl_hours = max(0.0, float(ttl_hours))
        self._directory.mkdir(parents=True, exist_ok=True)

    @property
    def directory(self) -> Path:
        return self._directory

    def _path(self, key: str) -> Path:
        return self._directory / f"{key}.json.gz"

    def get(self, key: str) -> Optional[Any]:
        path = self._path(key)
        if not path.exists():
            return None
        try:
            if self._ttl_hours <= 0:
                return None
            age_hours = (time.time() - path.stat().st_mtime) / 3600.0
            if age_hours > self._ttl_hours:
                return None
            data = zlib.decompress(path.read_bytes())
            return json.loads(data.decode("utf-8"))
        except Exception:
            return None

    def set(self, key: str, value: Any) -> None:
        try:
            raw = json.dumps(value, ensure_ascii=False).encode("utf-8")
            path = self._path(key)
            path.write_bytes(zlib.compress(raw, level=1))
        except Exception:
            pass

    def clear(self) -> int:
        if not self._directory.exists():
            return 0
        count = len(list(self._directory.glob("*.json.gz")))
        shutil.rmtree(self._directory, ignore_errors=True)
        self._directory.mkdir(parents=True, exist_ok=True)
        return count

    def cached(self, key: str, compute: Callable[[], Any]) -> Any:
        """Return cached value for ``key`` or compute, store and return it."""
        cached = self.get(key)
        if cached is not None:
            return cached
        value = compute()
        if value is not None:
            self.set(key, value)
        return value