from __future__ import annotations

"""Contact intelligence engine.

Deterministic, fully local extraction of structured contact facts (owner,
address, postal code, country, opening hours, social profiles, contact page
and form URLs, service areas) from already-fetched page HTML. No network, no
LLM, no DB access; the pipeline runs it before boilerplate removal so
contact-rich markup (headers, footers, forms, social icons) is still present.
"""

from src.contact.extractor import (
    extract_contact_signals,
    extract_contact_signals_from_crawl,
    extract_contact_signals_from_fetch,
)
from src.contact.schema import ContactSignals, merge_contact_signals

__all__ = [
    "ContactSignals",
    "extract_contact_signals",
    "extract_contact_signals_from_crawl",
    "extract_contact_signals_from_fetch",
    "merge_contact_signals",
]
