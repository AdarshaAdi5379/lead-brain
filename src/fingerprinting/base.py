from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Iterator, Optional

# Deterministic, data-driven signal registry for technology detection.
#
# Signals are combined (multiple weak signals build confidence). Nothing here
# calls an LLM or external service; the whole engine is pure description.

_ALLOWED_KINDS = {
    "generator",  # regex against <meta name="generator" content>
    "meta",       # regex against a readable meta name attribute's content
    "html",       # regex against the raw homepage HTML
    "script",     # regex against the set of <script src> URLs
    "style",      # regex against the set of stylesheet hrefs
    "global",     # regex against inline JS (globals / boot time calls)
    "header",     # regex against a response header (target -> name regex)
    "cookie",     # regex against a cookie name
    "class",      # regex against the homepage class names
    "id",         # regex against the homepage DOM ids
    "canonical",  # regex against the canonical URL
    "path",       # known-path probe (only used when endpoint probing is on)
}

CATEGORY_LABELS = {
    "cms": "CMS",
    "frontend": "Framework",
    "backend": "Backend",
    "hosting": "Hosting/CDN",
    "analytics": "Analytics",
    "libraries": "Library",
    "search": "Search",
    "payment": "Payments",
    "shopping": "Shopping",
}

# Only technologies we can confidently map to the extraction schema's platform enum.
PLATFORM_FROM_TECHNOLOGY = {
    "WordPress": "wordpress",
    "Wix": "wix",
    "Squarespace": "squarespace",
    "Shopify": "shopify",
    "Weebly": "weebly",
}


class FingerprintError(RuntimeError):
    """Raised when the fingerprint catalog or a signal is malformed."""


@dataclass(frozen=True)
class Signal:
    """A single deterministic evidence check.

    ``kind`` selects the evidence source to scan; ``pattern`` is a case
    insensitive regex used for the match (except for ``path`` kinds).
    """

    kind: str
    weight: int = 25
    pattern: str = ""
    target: str = ""
    path: str = ""
    hint: str = ""

    def __post_init__(self) -> None:
        if self.kind not in _ALLOWED_KINDS:
            raise FingerprintError(f"unknown signal kind: {self.kind!r}")
        if not (isinstance(self.weight, int) and self.weight > 0):
            raise FingerprintError(f"signal weight must be a positive int: {self.weight!r}")
        if self.kind == "path" and not self.path:
            raise FingerprintError("path signal requires a path")

    def label(self) -> str:
        if self.hint:
            return self.hint
        if self.kind == "path":
            return f"path {self.path}"
        parts = [self.kind, self.target or "", self.pattern or ""]
        return ":".join(p for p in parts if p)


@dataclass(frozen=True)
class Technology:
    """One technology entry: name, category and the signals that detect it."""

    name: str
    category: str
    signals: tuple[Signal, ...] = ()

    def __post_init__(self) -> None:
        if not (self.name or "").strip():
            raise FingerprintError("technology name cannot be empty")
        if self.category not in CATEGORY_LABELS:
            raise FingerprintError(f"unknown category {self.category!r} for {self.name!r}")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Technology":
        name = str(data.get("name", "")).strip()
        category = str(data.get("category", "")).strip()
        raw_signals = data.get("signals") or []
        signals = tuple(_build_signal(s) for s in raw_signals if isinstance(s, dict))
        return cls(name=name, category=category, signals=signals)


@dataclass(frozen=True)
class Detection:
    name: str
    category: str
    confidence: int
    evidence: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "technology_name": self.name,
            "category": self.category,
            "confidence": self.confidence,
            "evidence": list(self.evidence),
        }


class FingerprintCatalog:
    """Registry of technologies loaded from a JSON fingerprint database.

    Registering a new technology is a data change (JSON) or an in-code
    ``register_from_dict`` — no detection logic changes.
    """

    def __init__(self, technologies: Iterable[Technology] = ()) -> None:
        self._items: dict[tuple[str, str], Technology] = {}
        self._order: list[tuple[str, str]] = []
        for technology in technologies:
            self.register(technology)

    def register(self, technology: Technology) -> None:
        key = (technology.category, technology.name)
        if key not in self._items:
            self._order.append(key)
        self._items[key] = technology

    def register_from_dict(self, data: dict[str, Any]) -> None:
        self.register(Technology.from_dict(data))

    def __iter__(self) -> Iterator[Technology]:
        for key in self._order:
            yield self._items[key]

    def __len__(self) -> int:
        return len(self._items)

    def all(self) -> list[Technology]:
        return [self._items[key] for key in self._order]

    def get(self, category: str, name: str) -> Optional[Technology]:
        return self._items.get((category, name))


def _build_signal(data: dict[str, Any]) -> Signal:
    signal = Signal(
        kind=str(data.get("kind", "")).strip(),
        weight=int(data.get("weight", 25)),
        pattern=str(data.get("pattern", "")).strip(),
        target=str(data.get("target", "")).strip(),
        path=str(data.get("path", "")).strip(),
        hint=str(data.get("hint", "")).strip(),
    )
    return signal


def load_catalog(path: Optional[Path] = None) -> FingerprintCatalog:
    """Load technologies from a JSON catalog (list or {"technologies": [...]})."""
    path = Path(path) if path is not None else Path(__file__).resolve().parent / "data" / "fingerprints.json"
    if not path.exists():
        raise FingerprintError(f"Fingerprint catalog not found: {path}")

    try:
        with path.open("r", encoding="utf-8") as handle:
            raw = json.load(handle)
    except (OSError, ValueError) as exc:
        raise FingerprintError(f"Could not read fingerprint catalog {path}: {exc}") from exc

    if isinstance(raw, dict):
        technologies = raw.get("technologies") or []
    elif isinstance(raw, list):
        technologies = raw
    else:
        raise FingerprintError("fingerprint catalog must be a list or a parsed object")

    catalog = FingerprintCatalog()
    for entry in technologies:
        if not isinstance(entry, dict):
            raise FingerprintError(f"invalid fingerprint entry: {entry!r} ({path})")
        catalog.register(Technology.from_dict(entry))
    return catalog