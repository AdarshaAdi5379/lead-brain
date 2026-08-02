from __future__ import annotations

import hashlib
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, Optional

from src.settings import (
    NOMINATIM_DELAY_SECONDS,
    NOMINATIM_MAX_RETRIES,
    OSM_USER_AGENT,
    OVERPASS_DELAY_SECONDS,
    OVERPASS_MAX_RETRIES,
    OVERPASS_RETRY_BACKOFF_SECONDS,
)


def _headers() -> dict[str, str]:
    return {"User-Agent": OSM_USER_AGENT, "Accept": "application/json"}


class HttpBackoff:
    """Politely talks to a public free HTTP endpoint.

    Enforces a trailing delay between requests (rate limiting) and retries
    transient failures (429/5xx/timeouts) with exponential backoff. One
    instance should be shared per endpoint so an entire run respects the
    server's rate limit.
    """

    def __init__(self, *, delay: float, max_retries: int, backoff: float) -> None:
        self.delay = max(0.0, float(delay))
        self.max_retries = max(0, int(max_retries))
        self.backoff = max(0.0, float(backoff))
        self._last_request = 0.0

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_request
        if elapsed < self.delay:
            time.sleep(self.delay - elapsed)

    @staticmethod
    def _retryable(exc: BaseException) -> bool:
        if isinstance(exc, urllib.error.HTTPError):
            return exc.code in {429, 500, 502, 503, 504}
        return isinstance(exc, (urllib.error.URLError, TimeoutError, OSError))

    def _fetch(self, url: str, body: Optional[bytes]) -> dict[str, Any]:
        last_error: Optional[BaseException] = None
        for attempt in range(self.max_retries + 1):
            self._throttle()
            try:
                request = urllib.request.Request(url, data=body, headers=_headers())
                with urllib.request.urlopen(request, timeout=30) as response:
                    raw = response.read().decode("utf-8", errors="replace")
                self._last_request = time.monotonic()
                return json.loads(raw)
            except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError) as exc:
                last_error = exc
                if attempt >= self.max_retries or not self._retryable(exc):
                    break
                time.sleep(self.backoff * (2**attempt))
            except json.JSONDecodeError as exc:
                raise ValueError(f"Non-JSON response from {url}: {exc}") from exc

        if isinstance(last_error, urllib.error.HTTPError):
            raise RuntimeError(
                f"HTTP {last_error.code} from {url}: {last_error.reason}"
            ) from last_error
        raise RuntimeError(f"Request to {url} failed: {last_error}") from last_error

    def get_json(self, url: str, params: Optional[Dict[str, Any]] = None) -> dict[str, Any]:
        query = urllib.parse.urlencode(params or {})
        return self._fetch(f"{url}?{query}" if query else url, body=None)

    def post_form(self, url: str, data: Dict[str, Any]) -> dict[str, Any]:
        body = urllib.parse.urlencode(data).encode("utf-8")
        return self._fetch(url, body=body)


def cache_key(*parts: Any) -> str:
    """Stable short hash for caching providers' requests/API."""
    payload = "|".join(str(p) for p in parts)
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()