from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field


@dataclass
class EnrichmentReport:
    """Concise per-run counts for the enrichment pass."""

    processed: int = 0
    not_needed: int = 0
    found: int = 0
    not_found: int = 0
    low_confidence: int = 0
    failed: int = 0
    sources: Counter = field(default_factory=Counter)

    def record(self, status: str, source: str | None = None) -> None:
        if status == "found":
            self.found += 1
        elif status == "not_found":
            self.not_found += 1
        elif status == "low_confidence":
            self.low_confidence += 1
        elif status == "failed":
            self.failed += 1
        elif status == "not_needed":
            self.not_needed += 1
        if status != "not_needed":
            self.processed += 1
        if source:
            self.sources[source] += 1

    def to_log_summary(self) -> str:
        source_details = ", ".join(
            f"{name}={count}" for name, count in sorted(self.sources.items())
        )
        return (
            f"processed={self.processed} found={self.found} "
            f"not_found={self.not_found} low_confidence={self.low_confidence} "
            f"failed={self.failed} skipped_with_website={self.not_needed}"
            + (f" sources={source_details}" if source_details else "")
        )