from __future__ import annotations

from typing import Any, Optional

from src.chat.base import RetrievedContext
from src.chat.safety import sanitize_text
from src.contact.helpers import service_areas_from

# Reusable context builder: transforms retrieved rows into a compact, labelled
# text block per lead and assembles them into one bounded <lead_data> section.
# The block only ever contains facts from the database — never instructions.

MAX_BLOCK_CHARS = 1800


def build_lead_block(intel: dict[str, Any], *, rationale: Optional[str] = None) -> Optional[str]:
    """One compact, information-rich text block for a lead (None when missing)."""
    lead = intel.get("lead")
    if not lead:
        return None

    score = intel.get("score") or {}
    seo = intel.get("seo") or {}
    visual = intel.get("visual") or {}
    opportunities = intel.get("opportunities") or []
    detections = intel.get("detections") or []

    lines: list[str] = []
    name = sanitize_text(lead.get("business_name")) or str(lead.get("id"))
    lines.append(f"Business: {name}")

    location = ", ".join(
        part
        for part in (lead.get("city"), lead.get("state"), lead.get("country"))
        if part
    )
    meta = []
    if lead.get("category"):
        meta.append(f"category={sanitize_text(lead.get('category'))}")
    if location:
        meta.append(f"location={sanitize_text(location)}")
    if lead.get("source"):
        meta.append(f"source={sanitize_text(lead.get('source'))}")
    lines.append(" | ".join(meta))

    if lead.get("website_url"):
        lines.append(f"Website: {sanitize_text(lead.get('website_url'))}")

    tech = []
    for part in (lead.get("platform"), lead.get("complexity"), lead.get("load_speed")):
        if part and str(part) != "unknown":
            tech.append(str(part))
    tech += [
        f"{sanitize_text(d.get('technology_name'))} ({d.get('confidence')}%)"
        for d in detections[:4]
        if d.get("technology_name")
    ]
    if tech:
        lines.append("Technology: " + ", ".join(dict.fromkeys(tech)))

    if score.get("final_score") is not None:
        lines.append(
            f"Lead score: {score['final_score']}/100 ({score.get('priority_label') or 'unknown'})"
        )
        for reason in (score.get("top_positive_reasons") or [])[:3]:
            lines.append(f"  + {sanitize_text(reason)}")
        for reason in (score.get("top_negative_reasons") or [])[:3]:
            lines.append(f"  - {sanitize_text(reason)}")
        if score.get("recommended_outreach_angle"):
            lines.append(f"Outreach angle: {sanitize_text(score.get('recommended_outreach_angle'))}")

    if seo.get("site_score") is not None:
        issues = " ".join(
            sanitize_text(issue.get("reason")) if isinstance(issue, dict) else sanitize_text(issue)
            for issue in (seo.get("severity_summary") or [])[:3]
        )
        lines.append(
            f"SEO: {seo['site_score']}/100 ({seo.get('overall_health') or 'unknown'})"
            + (f" — {issues}" if issues else "")
        )

    if visual.get("visual_score") is not None:
        lines.append(
            f"Visual: {visual['visual_score']}/100 ({visual.get('visual_health_label') or 'unknown'})"
        )

    if opportunities:
        top = opportunities[0]
        services = ", ".join(
            str(service) for service in (top.get("recommended_services") or [])[:2]
        )
        lines.append(
            f"Top opportunity: {sanitize_text(top.get('label'))} "
            f"({top.get('score')}/100, {top.get('severity') or 'unknown'}, "
            f"impact={top.get('business_impact') or 'unknown'})"
        )
        if services:
            lines.append(f"  services: {services}")
        for evidence in (top.get("evidence") or [])[:2]:
            lines.append(f"  - {sanitize_text(evidence)}")

    contact = []
    if lead.get("phone"):
        contact.append(f"phone={sanitize_text(lead.get('phone'))}")
    elif not lead.get("website_url"):
        contact.append("phone=not stored")
    if lead.get("email"):
        contact.append(f"email={sanitize_text(lead.get('email'))}")
    elif not lead.get("website_url"):
        contact.append("email=not stored")
    if lead.get("owner_name"):
        contact.append(f"owner={sanitize_text(lead.get('owner_name'))}")
    if lead.get("postal_code"):
        contact.append(f"postal code={sanitize_text(lead.get('postal_code'))}")
    if contact:
        lines.append("Contact: " + ", ".join(contact))

    if lead.get("address"):
        lines.append(f"Address: {sanitize_text(lead.get('address'))}")

    social = [
        f"{field[: -len('_url')]}={sanitize_text(lead.get(field))}"
        for field in (
            "facebook_url",
            "instagram_url",
            "linkedin_url",
            "twitter_url",
            "youtube_url",
            "whatsapp_url",
        )
        if lead.get(field)
    ]
    if social:
        lines.append("Social: " + ", ".join(social))

    for label, key in (
        ("Opening hours", "opening_hours"),
        ("Contact page", "contact_page_url"),
        ("Contact form", "contact_form_url"),
        ("Maps", "google_maps_url"),
    ):
        if lead.get(key):
            lines.append(f"{label}: {sanitize_text(lead.get(key))}")

    service_areas = service_areas_from(lead)
    if service_areas:
        lines.append("Service areas: " + ", ".join(service_areas))

    timestamps = []
    for label, value in (
        ("extracted", lead.get("extracted_at")),
        ("scored", score.get("scored_at")),
        ("seo audit", seo.get("audited_at")),
        ("visual audit", visual.get("audited_at")),
    ):
        if value:
            timestamps.append(f"{label}={sanitize_text(value)}")
    if timestamps:
        lines.append("Timestamps: " + ", ".join(timestamps))

    if rationale:
        lines.append(f"Why selected: {sanitize_text(rationale)}")

    block = "\n".join(part for part in lines if part)
    return sanitize_text(block, max_chars=MAX_BLOCK_CHARS)


def build_context_block(
    context: RetrievedContext,
    *,
    max_leads: int,
    max_chars: int,
) -> str:
    """Assemble retrieved leads into one budgeted <lead_data> section.

    Blocks are added in ranking order until the char budget is exhausted; a
    note is included when some retrieved leads were omitted.
    """
    blocks: list[str] = []
    used = 0
    total = len(context.retrieved_leads)
    for index, retrieved in enumerate(context.retrieved_leads[:max_leads], start=1):
        block = build_lead_block(retrieved.intel, rationale=retrieved.rationale)
        if not block:
            continue
        framed = f"[{index}] {block}"
        if used + len(framed) > max_chars:
            break
        blocks.append(framed)
        used += len(framed)

    body = "\n\n".join(blocks)
    if not body:
        return ""
    if total > len(blocks):
        body += f"\n\n(Note: {total - len(blocks)} more retrieved lead(s) omitted from budget.)"
    return body