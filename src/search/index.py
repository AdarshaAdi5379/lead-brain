from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from src.contact.helpers import service_areas_from
from src.search.cache import document_hash

# Deterministic document builder: every lead becomes exactly one searchable
# semantic document (plus a flat, whitelisted metadata dict used for filtering
# and result cards). Pure functions over the stored intelligence — no network,
# no LLM, no re-crawling.

# Allowed metadata keys emitted for a lead (whitelist; never echo raw JSON).
METADATA_KEYS = (
    "lead_id",
    "business_name",
    "website_url",
    "website_present",
    "category",
    "city",
    "state",
    "country",
    "platform",
    "source",
    "priority",
    "lead_score",
    "seo_score",
    "visual_score",
    "opportunity_score",
    "opportunity_count",
    "extraction_success",
    "updated_at",
    "technologies",
)


@dataclass(frozen=True)
class SearchDocument:
    """One searchable unit: combined text + filter metadata + content hash."""

    lead_id: int
    text: str
    metadata: dict[str, Any]
    document_hash: str


_SOCIAL_FIELDS = (
    ("facebook", "facebook_url"),
    ("instagram", "instagram_url"),
    ("linkedin", "linkedin_url"),
    ("twitter", "twitter_url"),
    ("youtube", "youtube_url"),
    ("whatsapp", "whatsapp_url"),
)


def build_lead_document(intel: dict[str, Any]) -> Optional[SearchDocument]:
    """Build the semantic document for one lead's intelligence dict.

    Returns None when the lead row itself is missing (defensive; callers should
    have already filtered those out).
    """
    lead: Optional[dict[str, Any]] = intel.get("lead")
    if not lead:
        return None
    lead_id = int(lead["id"])
    text = _document_text(lead_id, lead, intel)
    metadata = _document_metadata(lead, intel)
    return SearchDocument(
        lead_id=lead_id,
        text=text,
        metadata=metadata,
        document_hash=document_hash(text),
    )


def _document_text(lead_id: int, lead: dict[str, Any], intel: dict[str, Any]) -> str:
    """One labelled semantic document combining every collected signal."""
    sections: list[str] = []

    name = str(lead.get("business_name") or "").strip()
    category = str(lead.get("category") or "").strip()
    location = ", ".join(
        part
        for part in (
            str(lead.get("city") or "").strip(),
            str(lead.get("state") or "").strip(),
            str(lead.get("country") or "").strip(),
        )
        if part
    )
    sections.append("BUSINESS: " + " | ".join(part for part in (name, category, location) if part))
    if not (name or category or location):
        sections.append(f"BUSINESS: lead {lead_id}")

    location_parts = [
        part
        for part in (
            str(lead.get("address") or "").strip(),
            str(lead.get("postal_code") or "").strip(),
            str(lead.get("google_maps_url") or "").strip(),
        )
        if part
    ]
    if location_parts:
        sections.append("LOCATION: " + " | ".join(location_parts))

    service_areas = service_areas_from(lead)
    if service_areas:
        sections.append("SERVICES: " + ", ".join(service_areas))

    website = str(lead.get("website_url") or "").strip()
    phone = str(lead.get("phone") or "").strip()
    email = str(lead.get("email") or "").strip()

    contact_parts = [
        part
        for part in (
            f"owner: {str(lead.get('owner_name') or '').strip()}" if lead.get("owner_name") else "",
            f"phone: {phone}" if phone else "",
            f"email: {email}" if email else "",
            f"website: {website}" if website else "",
            f"contact page: {str(lead.get('contact_page_url') or '').strip()}"
            if lead.get("contact_page_url")
            else "",
            f"contact form: {str(lead.get('contact_form_url') or '').strip()}"
            if lead.get("contact_form_url")
            else "",
        )
        if part
    ]
    if not phone:
        contact_parts.append("no phone")
    if not email:
        contact_parts.append("no email")
    if contact_parts:
        sections.append("CONTACT: " + " | ".join(contact_parts))

    social_parts = [
        f"{platform}: {str(lead.get(field) or '').strip()}"
        for platform, field in _SOCIAL_FIELDS
        if lead.get(field)
    ]
    if social_parts:
        sections.append("SOCIAL: " + " | ".join(social_parts))

    if lead.get("opening_hours"):
        sections.append("OPENING HOURS: " + str(lead.get("opening_hours")).strip())

    platform = str(lead.get("platform") or "").strip()
    complexity = str(lead.get("complexity") or "").strip()
    load_speed = str(lead.get("load_speed") or "").strip()
    tech_parts = [part for part in (platform, complexity, load_speed) if part and part != "unknown"]
    for detection in intel.get("detections", []):
        tech_parts.append(str(detection.get("technology_name") or "").strip())
    tech_parts = [part for part in tech_parts if part]
    if tech_parts:
        sections.append("TECHNOLOGY: " + ", ".join(dict.fromkeys(tech_parts)))
    elif not website:
        sections.append("TECHNOLOGY: no website detected")

    seo = intel.get("seo")
    if seo:
        seo_parts = [
            f"SEO: {int(seo.get('site_score') or 0)}/100 ({seo.get('overall_health') or 'unknown'})"
        ]
        for issue in seo.get("severity_summary") or []:
            reason = str(issue.get("reason") or "").strip() if isinstance(issue, dict) else ""
            if reason:
                seo_parts.append("- " + reason)
        sections.append("\n".join(seo_parts))

    visual = intel.get("visual")
    if visual:
        visual_parts = [
            f"VISUAL: {int(visual.get('visual_score') or 0)}/100 ({visual.get('visual_health_label') or 'unknown'})"
        ]
        summary = str(visual.get("summary") or "").strip()
        if summary:
            visual_parts.append("- " + summary)
        sections.append("\n".join(visual_parts))

    opportunities = intel.get("opportunities") or []
    if opportunities:
        opp_parts = ["OPPORTUNITIES:"]
        for item in opportunities[:5]:
            label = str(item.get("label") or item.get("category") or "").strip()
            score = int(item.get("score") or 0)
            opp_parts.append(f"- {label} ({score}/100)")
            for evidence in (item.get("evidence") or [])[:2]:
                evidence = str(evidence).strip()
                if evidence:
                    opp_parts.append("    - " + evidence)
        sections.append("\n".join(opp_parts))

    score = intel.get("score")
    if score:
        score_parts = [
            f"SCORING: {int(score.get('final_score') or 0)}/100 ({score.get('priority_label') or 'unknown'})"
        ]
        for reason in (score.get("top_positive_reasons") or [])[:3]:
            reason = str(reason).strip()
            if reason:
                score_parts.append("+ " + reason)
        for reason in (score.get("top_negative_reasons") or [])[:3]:
            reason = str(reason).strip()
            if reason:
                score_parts.append("- " + reason)
        angle = str(score.get("recommended_outreach_angle") or "").strip()
        if angle:
            score_parts.append("Outreach angle: " + angle)
        sections.append("\n".join(score_parts))

    return "\n\n".join(sections)


def _document_metadata(
    lead: dict[str, Any], intel: dict[str, Any]
) -> dict[str, Any]:
    """Flat, whitelisted metadata for filtering and result cards."""
    website = str(lead.get("website_url") or "").strip()

    opportunities = intel.get("opportunities") or []
    opportunity_score: Optional[int] = None
    for item in opportunities:
        score = _int_or_none(item.get("score"))
        if score is not None and (opportunity_score is None or score > opportunity_score):
            opportunity_score = score

    score = intel.get("score")
    priority = str(lead.get("priority") or "").strip() or (
        str(score.get("priority_label") or "").strip() if score else ""
    )

    return {
        "lead_id": int(lead["id"]),
        "business_name": str(lead.get("business_name") or "") or None,
        "website_url": website or None,
        "website_present": bool(website),
        "category": str(lead.get("category") or "") or None,
        "city": str(lead.get("city") or "") or None,
        "state": str(lead.get("state") or "") or None,
        "country": str(lead.get("country") or "") or None,
        "platform": str(lead.get("platform") or "") or None,
        "source": str(lead.get("source") or "") or None,
        "priority": priority or None,
        "lead_score": _int_or_none(lead.get("score")),
        "seo_score": _int_or_none((intel.get("seo") or {}).get("site_score")),
        "visual_score": _int_or_none(
            (intel.get("visual") or {}).get("visual_score")
        ),
        "opportunity_score": opportunity_score,
        "opportunity_count": len(opportunities),
        "extraction_success": bool(lead.get("extraction_success")),
        "updated_at": str(lead.get("extracted_at") or ""),
        "technologies": [
            str(detection.get("technology_name") or "").strip().lower()
            for detection in intel.get("detections", [])
            if str(detection.get("technology_name") or "").strip()
        ],
    }


def _int_or_none(value: Any) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
