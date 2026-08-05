from __future__ import annotations

"""Contact intelligence engine.

Deterministic, fully local extraction of structured contact facts (owner,
address, postal code, country, opening hours, social profiles, contact page
and form URLs, service areas) from already-fetched page HTML. No network, no
LLM, no DB access; the pipeline runs it before boilerplate removal so
contact-rich markup (headers, footers, forms, social icons) is still present.
"""

from src.contact.display import CONTACT_FIELDS, group_contact_facts, lead_contact_dict
from src.contact.extractor import (
    extract_contact_signals,
    extract_contact_signals_from_crawl,
    extract_contact_signals_from_fetch,
)
from src.contact.microdata import extract_microdata
from src.contact.recovery import extract_email_candidates, extract_phone_candidates
from src.contact.schema import ContactSignals, merge_contact_signals
from src.contact.sources import (
    ContactCandidate,
    better_contact,
    pick_across_sources,
    pick_best_email,
    pick_best_phone,
)

__all__ = [
    "CONTACT_FIELDS",
    "ContactCandidate",
    "ContactSignals",
    "better_contact",
    "extract_contact_signals",
    "extract_contact_signals_from_crawl",
    "extract_contact_signals_from_fetch",
    "extract_email_candidates",
    "extract_microdata",
    "extract_phone_candidates",
    "group_contact_facts",
    "lead_contact_dict",
    "merge_contact_signals",
    "pick_across_sources",
    "pick_best_email",
    "pick_best_phone",
]
