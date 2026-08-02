from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DiscoveryQuery:
    """A single user-facing discovery request: find businesses of a
    ``category`` within a human-readable ``location`` (e.g. "Austin, TX")."""

    category: str
    location: str