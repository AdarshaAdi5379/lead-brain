from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class HeaderEvidence:
    """Normalized response headers parsed from a live fetch.

    Header names are lower-cased; matchers accept case insensitive regexes.
    """

    items: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        # Nothing to fix: items are stored as lowercase name -> value on build.
        pass

    def match(self, target: str, pattern: str) -> str | None:
        """Signal matcher for header evidence.

        ``target`` is a regex against the (lowercased) header name; ``pattern``
        is a regex against the value. If either is empty the element is
        treated as "always matched" so a name-only or value-only signal works.
        """
        name_rx = re.compile(target, re.IGNORECASE)
        value_rx = re.compile(pattern, re.IGNORECASE)
        for name, value in self.items:
            name_ok = not target or bool(name_rx.search(name))
            value_ok = not pattern or bool(value_rx.search(value))
            if name_ok and value_ok:
                return f"{name}: {value}"
        return ""


def build_evidence(headers: dict[str, str] | None) -> HeaderEvidence:
    """Normalize a raw {Header: value} dict into HeaderEvidence."""
    if not headers:
        return HeaderEvidence()
    items = tuple((str(k).lower().strip(), str(v).strip()) for k, v in headers.items() if v)
    return HeaderEvidence(items=items)