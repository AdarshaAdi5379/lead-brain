from __future__ import annotations

import html
from typing import Any, Optional

from src.map.map_filters import score_group

# Marker styling and popup payloads. All copy is built from sanitized values so
# popup content can never carry script injection or unsafe URLs.

MARKER_COLORS: dict[str, str] = {
    "Hot": "red",
    "Warm": "orange",
    "Cold": "blue",
    "Avoid": "gray",
}


def marker_color(score: Any) -> str:
    """folium color name for a lead score (Hot/Warm/Cold/Avoid)."""
    return MARKER_COLORS.get(score_group(score), "gray")


def legend_items() -> list[tuple[str, str]]:
    """(label, color) pairs for the on-page legend, in priority order."""
    return [(label, color) for label, color in MARKER_COLORS.items()]


def website_presence(url: Optional[str]) -> str:
    return "Yes" if str(url or "").strip().startswith(("http://", "https://")) else "No"


def contact_presence(has_contact: bool) -> str:
    return "Yes" if has_contact else "No"


def marker_payload(lead: Any) -> dict[str, Any]:
    """Plain, dashboard-friendly summary of one lead (for tooltips/tables)."""
    score = lead.lead_score
    return {
        "id": int(lead.id),
        "business_name": str(lead.business_name or f"Lead #{lead.id}"),
        "category": str(lead.category or ""),
        "city": str(lead.city or ""),
        "state": str(lead.state or ""),
        "platform": str(lead.platform or ""),
        "lead_score": score,
        "priority_label": str(lead.priority_label or score_group(score)),
        "opportunity_score": int(lead.opportunity_score or 0),
        "website_url": str(lead.website_url or ""),
        "has_website": website_presence(lead.website_url),
        "has_contact": contact_presence(bool(lead.has_contact)),
    }


def _safe_url(url: Optional[str]) -> Optional[str]:
    text = str(url or "").strip()
    if text.startswith(("http://", "https://")):
        return text
    return None


def popup_html(lead: Any) -> str:
    """Escaped, link-safe HTML for a marker popup."""
    e = html.escape
    name = e(str(lead.business_name or f"Lead #{lead.id}"))
    category = e(str(lead.category or "") or "—")
    location = e(", ".join(p for p in (lead.city, lead.state) if p) or "—")
    platform = e(str(lead.platform or "") or "—")
    lead_score = "—" if lead.lead_score is None else str(lead.lead_score)
    priority = e(str(lead.priority_label or score_group(lead.lead_score)))
    opportunity_score = str(int(lead.opportunity_score or 0))
    url = _safe_url(lead.website_url)
    if url is None:
        website = "No website"
    else:
        website = (
            f'<a href="{e(url, quote=True)}" target="_blank" rel="noopener noreferrer">'
            "website</a>"
        )
    lines = [
        f"<b>{name}</b>",
        f"Category: {category}",
        f"Location: {location}",
        f"Platform: {platform}",
        f"Lead score: {lead_score} ({priority})",
        f"Opportunity score: {opportunity_score}",
        f"Website: {website}",
        f"Contact info: {contact_presence(bool(lead.has_contact))}",
    ]
    return "<br>".join(f"<div>{line}</div>" for line in lines)