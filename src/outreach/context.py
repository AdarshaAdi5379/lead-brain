from __future__ import annotations

import sqlite3
from typing import Any, Mapping, Optional

from src.contact.helpers import service_areas_from
from src.search.summarizer import build_context
from src.storage import search as search_storage

# Outreach context builder: a rich, deterministic digest of one lead's
# collected intelligence, shaped for a future outreach generator.
#
# It only ever packs collected facts — it never writes email copy, never
# invents content, and never calls the network or the LLM. Empty/NULL facts
# are dropped so the generator receives only what was actually collected.

_SOCIAL_FIELDS = (
    ("facebook", "facebook_url"),
    ("instagram", "instagram_url"),
    ("linkedin", "linkedin_url"),
    ("twitter", "twitter_url"),
    ("youtube", "youtube_url"),
    ("whatsapp", "whatsapp_url"),
)


def build_outreach_context(intel: dict[str, Any]) -> Optional[dict[str, Any]]:
    """Structured outreach context for one lead (None when the lead is missing)."""
    lead = intel.get("lead")
    if not lead:
        return None

    summary = build_context(intel) or {}
    opportunities = summary.get("opportunities") or {}
    opportunity_items = opportunities.get("items") or []
    top_item = opportunity_items[0] if opportunity_items else None

    return {
        "business": _drop_empty(
            {
                "business_name": lead.get("business_name"),
                "category": lead.get("category"),
            }
        ),
        "location": _drop_empty(
            {
                "city": lead.get("city"),
                "state": lead.get("state"),
                "country": lead.get("country"),
                "address": lead.get("address"),
                "postal_code": lead.get("postal_code"),
            }
        ),
        "services": service_areas_from(lead),
        "contact": _drop_empty(
            {
                "owner_name": lead.get("owner_name"),
                "phone": lead.get("phone"),
                "email": lead.get("email"),
                "website_url": lead.get("website_url"),
                "contact_page_url": lead.get("contact_page_url"),
                "contact_form_url": lead.get("contact_form_url"),
                "google_maps_url": lead.get("google_maps_url"),
            }
        ),
        "social_presence": _drop_empty(
            {
                platform: lead.get(field)
                for platform, field in _SOCIAL_FIELDS
            }
        ),
        "opening_hours": str(lead.get("opening_hours") or "").strip() or None,
        "technology": summary.get("technology") or {},
        "seo": summary.get("seo") or {},
        "visual": summary.get("visual") or {},
        "opportunity_summary": {
            "count": int(opportunities.get("count") or 0),
            "opportunity_score": int(opportunities.get("opportunity_score") or 0),
            "top_opportunity": opportunities.get("top_opportunity"),
            "recommended_services": (
                list(top_item.get("recommended_services") or [])
                if top_item
                else []
            ),
        },
        "reachability": _reachability(lead),
    }


def _reachability(lead: Mapping[str, Any]) -> dict[str, Any]:
    """Which contact channels exist, so a generator can pick one safely."""
    has_email = bool(str(lead.get("email") or "").strip())
    has_phone = bool(str(lead.get("phone") or "").strip())
    has_whatsapp = bool(str(lead.get("whatsapp_url") or "").strip())
    has_contact_form = bool(str(lead.get("contact_form_url") or "").strip())
    return _drop_empty(
        {
            "email": has_email,
            "phone": has_phone,
            "whatsapp": has_whatsapp,
            "contact_form": has_contact_form,
            "best_contact_method": (
                "email" if has_email else ("whatsapp" if has_whatsapp else ("phone" if has_phone else None))
            ),
        }
    )


def outreach_context_text(context: dict[str, Any]) -> str:
    """Markdown rendering of the outreach context (neutral, LLM-friendly)."""
    lines: list[str] = []

    business = context.get("business") or {}
    title = business.get("business_name") or "Business"
    lines.append(f"# {title}")
    if business.get("category"):
        lines.append(f"- Category: {business['category']}")

    _lines_from(context, "location", lines)
    _lines_from(context, "contact", lines)

    services = context.get("services") or []
    if services:
        lines.append(f"- Service areas: {', '.join(services)}")

    social = context.get("social_presence") or {}
    if social:
        lines.append("## Social presence")
        for platform, url in social.items():
            lines.append(f"- {platform}: {url}")

    if context.get("opening_hours"):
        lines.append(f"- Opening hours: {context['opening_hours']}")

    technology = context.get("technology") or {}
    tech_parts = [
        part
        for part in (
            technology.get("platform"),
            technology.get("complexity"),
            technology.get("load_speed"),
        )
        if part and part != "unknown"
    ]
    for detection in technology.get("detections") or []:
        name = detection.get("name")
        if name:
            tech_parts.append(f"{name} ({detection.get('category')}, {detection.get('confidence')}%)")
    if tech_parts:
        lines.append("## Technology")
        lines.append(", ".join(tech_parts))

    seo = context.get("seo") or {}
    if seo.get("site_score") is not None:
        lines.append("## SEO")
        lines.append(f"- Score: {seo['site_score']}/100 ({seo.get('overall_health') or 'unknown'})")

    visual = context.get("visual") or {}
    if visual.get("visual_score") is not None:
        lines.append("## Visual")
        lines.append(
            f"- Score: {visual['visual_score']}/100 ({visual.get('visual_health_label') or 'unknown'})"
        )

    opportunity = context.get("opportunity_summary") or {}
    if opportunity.get("top_opportunity"):
        lines.append("## Opportunity summary")
        lines.append(
            f"- {opportunity['top_opportunity']} ({opportunity.get('opportunity_score') or 0}/100)"
        )
        services = opportunity.get("recommended_services") or []
        if services:
            lines.append(f"- Recommended services: {', '.join(services)}")

    return "\n".join(lines)


def outreach_context_for_lead(
    connection: sqlite3.Connection, lead_id: int
) -> Optional[dict[str, Any]]:
    """Load intelligence for one lead and build its outreach context."""
    intel = search_storage.lead_intelligence(connection, int(lead_id))
    if intel is None:
        return None
    return build_outreach_context(intel)


def _lines_from(context: dict[str, Any], key: str, lines: list[str]) -> None:
    for label, value in (context.get(key) or {}).items():
        if value is None:
            continue
        lines.append(f"- {_LABELS.get(label, label.replace('_', ' ').title())}: {value}")


_LABELS = {
    "owner_name": "Owner",
    "phone": "Phone",
    "email": "Email",
    "website_url": "Website",
    "contact_page_url": "Contact page",
    "contact_form_url": "Contact form",
    "google_maps_url": "Google Maps",
    "postal_code": "Postal code",
}


def _drop_empty(mapping: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in mapping.items() if _non_empty(value)}


def _non_empty(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, bool):
        return True
    if isinstance(value, (list, tuple)):
        return bool(value)
    return bool(str(value).strip())