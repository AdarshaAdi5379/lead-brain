from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class CookieEvidence:
    """Normalized cookies captured from the fetched context.

    ``items`` maps cookie name -> value (names lowercased for matching).
    """

    items: tuple[tuple[str, str], ...] = ()

    def match(self, pattern: str) -> str | None:
        rx = re.compile(pattern, re.IGNORECASE)
        for name, value in self.items:
            if rx.search(name):
                return f"{name}={value}"
        return ""


def build_cookie_evidence(cookies: list[dict] | None) -> CookieEvidence:
    """Normalize a list of cookie dicts (as returned by Playwright) into evidence."""
    if not cookies:
        return CookieEvidence()
    items: list[tuple[str, str]] = []
    for cookie in cookies:
        if not isinstance(cookie, dict):
            continue
        name = str(cookie.get("name") or "").strip().lower()
        value = str(cookie.get("value") or "").strip()
        if name:
            items.append((name, value))
    return CookieEvidence(items=tuple(items))