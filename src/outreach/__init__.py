from __future__ import annotations

from src.outreach.config import OutreachConfig, from_settings
from src.outreach.context import (
    build_outreach_context,
    outreach_context_for_lead,
    outreach_context_text,
)
from src.outreach.generator import (
    CONTACT_LABELS,
    CONTACT_METHODS,
    Fact,
    OutreachDraft,
    available_contact_methods,
    generate_outreach,
    select_contact_method,
    signal_facts,
)
from src.outreach.service import OutreachService

__all__ = [
    "CONTACT_LABELS",
    "CONTACT_METHODS",
    "Fact",
    "OutreachConfig",
    "OutreachDraft",
    "OutreachService",
    "available_contact_methods",
    "build_outreach_context",
    "from_settings",
    "generate_outreach",
    "outreach_context_for_lead",
    "outreach_context_text",
    "select_contact_method",
    "signal_facts",
]