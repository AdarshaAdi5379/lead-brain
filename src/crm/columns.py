from __future__ import annotations

from typing import Tuple

# Canonical column set for the local Excel CRM workbook (Phase 18).
#
# The workbook is the user-facing CRM layer: auto columns are filled from the
# project data on every refresh, manual columns are user-owned and always win
# on merge. The single "Leads" sheet holds one row per lead.

COLUMNS: Tuple[str, ...] = (
    "lead_id",
    "business_name",
    "category",
    "city",
    "state",
    "country",
    "website_url",
    "phone",
    "email",
    "address",
    "opening_hours",
    "facebook_url",
    "instagram_url",
    "linkedin_url",
    "twitter_url",
    "youtube_url",
    "whatsapp_url",
    "contact_page_url",
    "contact_form_url",
    "google_maps_url",
    "platform",
    "lead_score",
    "seo_score",
    "visual_score",
    "opportunity_score",
    "priority_label",
    "recommended_outreach_angle",
    "best_contact_method",
    "status",
    "last_contacted",
    "next_follow_up",
    "assigned_to",
    "notes",
)

# Columns the user may edit manually; these are never overwritten by a refresh
# unless an explicit full rebuild is requested.
MANUAL_COLUMNS: Tuple[str, ...] = (
    "status",
    "notes",
    "last_contacted",
    "next_follow_up",
    "assigned_to",
    "best_contact_method",
)

# Everything else is regenerated from SQLite on refresh.
AUTO_COLUMNS: Tuple[str, ...] = tuple(column for column in COLUMNS if column not in MANUAL_COLUMNS)

DEFAULT_STATUS: str = "New"

SHEET_NAME: str = "Leads"

URL_COLUMNS: Tuple[str, ...] = (
    "website_url",
    "facebook_url",
    "instagram_url",
    "linkedin_url",
    "twitter_url",
    "youtube_url",
    "whatsapp_url",
    "contact_page_url",
    "contact_form_url",
    "google_maps_url",
)

# Stored as ISO dates (YYYY-MM-DD) — Excel-readable, sortable, blank-safe.
DATE_COLUMNS: Tuple[str, ...] = ("last_contacted", "next_follow_up")
