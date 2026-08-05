from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping, Optional, Sequence, Tuple

from src.chat.llm import LLMBackend
from src.chat.safety import fenced_data, sanitize_text
from src.outreach import templates
from src.outreach.config import OutreachConfig, from_settings
from src.outreach.context import outreach_context_text
from src.outreach.renderer import compose_message
from src.outreach.validation import (
    extract_referenced_facts,
    validate_llm_message,
    validate_template_message,
)

# Grounded outreach generation. Both generation modes (deterministic template
# and local-LLM) consume the exact same outreach context object built by
# context.py. Facts are derived only from deterministic audit results; contact
# channels are selected by priority from what was actually collected. LLM
# drafts are validated before use and fall back to the template mode on any
# failure -- the pipeline never fabricates business details.


@dataclass(frozen=True)
class Fact:
    """One deterministic, audit-derived finding usable in outreach copy."""

    key: str
    label: str
    phrase: str


@dataclass(frozen=True)
class OutreachDraft:
    """The generated outreach message plus everything needed to explain it."""

    message: str
    style: str
    length: str
    mode: str
    contact_method: Optional[str]
    contact_target: Optional[str]
    facts_used: list[str]
    facts_available: list[str]
    warnings: list[str]
    valid: bool = True
    issues: Tuple[str, ...] = ()

    @property
    def contact_display(self) -> Optional[str]:
        if not self.contact_method:
            return None
        label = CONTACT_LABELS.get(self.contact_method, self.contact_method)
        if self.contact_target:
            return f"{label} ({self.contact_target})"
        return label


CONTACT_METHODS: Tuple[str, ...] = (
    "email",
    "linkedin",
    "facebook",
    "whatsapp",
    "contact_form",
    "phone",
)

CONTACT_LABELS: Mapping[str, str] = {
    "email": "Email",
    "linkedin": "LinkedIn",
    "facebook": "Facebook",
    "whatsapp": "WhatsApp",
    "contact_form": "Contact form",
    "phone": "Phone",
}

_AVAILABILITY_LABELS: Mapping[str, str] = {
    "email": "Contact email available",
    "linkedin": "LinkedIn profile available",
    "facebook": "Facebook page available",
    "whatsapp": "WhatsApp available",
    "contact_form": "Contact form available",
    "phone": "Contact phone available",
}

_AVAILABILITY_PHRASES: Mapping[str, str] = {
    "email": "the site lists a contact email",
    "linkedin": "the business is on LinkedIn",
    "facebook": "the business is on Facebook",
    "whatsapp": "the business is reachable on WhatsApp",
    "contact_form": "the site has a contact form",
    "phone": "the site lists a phone number",
}

# Deterministic issue text (from the SEO/visual audits) -> fact copy.
_ISSUE_FACTS: Mapping[str, Tuple[str, str]] = {
    "Weak mobile experience": ("weak_mobile", "a weak mobile experience"),
    "Cluttered layout": ("clutter", "a cluttered layout"),
    "Poor visual hierarchy": ("weak_hierarchy", "a weak visual hierarchy"),
    "Weak call-to-action": ("weak_cta", "a weak call-to-action"),
    "Outdated design": ("outdated_design", "a dated design"),
    "Weak visual presentation": ("weak_visual", "weak visual presentation"),
    "Weak SEO score": ("weak_seo", "weak search visibility"),
    "Missing meta descriptions": ("missing_meta", "missing meta descriptions"),
    "Missing page titles": ("missing_titles", "missing page titles"),
    "Missing structured data": ("missing_schema", "missing structured data"),
    "Missing canonical URLs": ("missing_canonical", "missing canonical URLs"),
    "Missing image alt text": ("missing_alt", "missing image alt text"),
    "Thin content on some pages": ("thin_content", "thin content"),
    "Duplicate page titles": ("dup_titles", "duplicate page titles"),
    "Multiple H1 headings on some pages": ("multi_h1", "multiple heading levels"),
    "Pages blocked from search results": ("noindex", "pages blocked from search"),
    "Mixed content on some pages": ("mixed_content", "mixed content"),
}


def signal_facts(context: Mapping[str, Any]) -> list[Fact]:
    """Deterministic, audit-only findings for one lead (ordered by impact)."""
    facts: list[Fact] = []
    contact = context.get("contact") or {}
    has_website = bool(str(contact.get("website_url") or "").strip())

    if not has_website:
        facts.append(
            Fact(
                key="no_website",
                label="No website found",
                phrase="no active website found",
            )
        )
        return _dedupe_facts(facts)

    for issue in context.get("top_visual_issues") or []:
        facts.append(_issue_fact(str(issue)))
    for issue in context.get("top_seo_issues") or []:
        facts.append(_issue_fact(str(issue)))

    technology = context.get("technology") or {}
    platform = str(technology.get("platform") or "").strip()
    if platform and platform.lower() != "unknown":
        facts.append(
            Fact(
                key=f"platform_{platform.lower()}",
                label=f"{platform} website",
                phrase=f"the site is built on {platform}",
            )
        )

    if not contact.get("contact_form_url"):
        facts.append(
            Fact(
                key="no_contact_form",
                label="No contact form",
                phrase="no contact form on the site",
            )
        )
    if not context.get("social_presence"):
        facts.append(
            Fact(
                key="no_social",
                label="No social presence",
                phrase="no social links on the site",
            )
        )

    seo = context.get("seo") or {}
    seo_score = seo.get("site_score")
    if platform and platform.lower() != "unknown" and seo_score is not None:
        if int(seo_score) < 60:
            facts.append(
                Fact(
                    key="modern_weak_local_seo",
                    label="Modern website with weak local SEO",
                    phrase="a modern website with weak local SEO",
                )
            )
    elif seo_score is not None and int(seo_score) < 50:
        if not any(fact.key == "weak_seo" for fact in facts):
            facts.append(
                Fact(
                    key="weak_seo",
                    label="Weak SEO",
                    phrase="weak search visibility",
                )
            )

    return _dedupe_facts(facts)


def _issue_fact(issue: str) -> Fact:
    mapping = _ISSUE_FACTS.get(issue)
    if mapping:
        return Fact(key=mapping[0], label=issue, phrase=mapping[1])
    phrase = issue.lower()
    if not phrase.endswith("."):
        phrase = f"{phrase} on the site"
    slug = re.sub(r"[^a-z0-9]+", "-", issue.lower()).strip("-")[:40] or "issue"
    return Fact(key=f"issue_{slug}", label=issue, phrase=phrase)


def _dedupe_facts(facts: Sequence[Fact]) -> list[Fact]:
    seen: set[str] = set()
    result: list[Fact] = []
    for fact in facts:
        if fact.key in seen:
            continue
        seen.add(fact.key)
        result.append(fact)
    return result


# --- contact selection -------------------------------------------------------


def _channel_target(context: Mapping[str, Any], method: str) -> Optional[str]:
    contact = context.get("contact") or {}
    social = context.get("social_presence") or {}
    field = {
        "email": ("contact", "email"),
        "linkedin": ("social", "linkedin"),
        "facebook": ("social", "facebook"),
        "whatsapp": ("social", "whatsapp"),
        "contact_form": ("contact", "contact_form_url"),
        "phone": ("contact", "phone"),
    }.get(method)
    if field is None:
        return None
    group, key = field
    source = contact if group == "contact" else social
    value = str(source.get(key) or "").strip()
    return value or None


def available_contact_methods(context: Mapping[str, Any]) -> list[str]:
    """Contact channels that actually exist, in outreach priority order."""
    reachability = context.get("reachability") or {}
    if reachability and any(reachability.get(method) for method in CONTACT_METHODS):
        return [method for method in CONTACT_METHODS if reachability.get(method)]
    return [
        method for method in CONTACT_METHODS if _channel_target(context, method)
    ]


def select_contact_method(
    context: Mapping[str, Any], preferred: str = "auto"
) -> Optional[Tuple[str, str]]:
    """Best available channel (priority order), or None when none exists."""
    available = available_contact_methods(context)
    if not available:
        return None
    if preferred and preferred != "auto" and preferred in available:
        chosen = preferred
    else:
        chosen = available[0]
    return (chosen, _channel_target(context, chosen) or "")


# --- generation --------------------------------------------------------------


def generate_outreach(
    context: Mapping[str, Any],
    *,
    style: str = "professional",
    length: str = "medium",
    contact_method: str = "auto",
    backend: Optional[LLMBackend] = None,
    config: Optional[OutreachConfig] = None,
) -> OutreachDraft:
    """Generate one outreach draft from a structured context (never raises)."""
    config = config or from_settings()
    style = style if style in templates.STYLES else config.default_style
    length = length if length in templates.LENGTHS else config.default_length

    facts = signal_facts(context)
    contact = select_contact_method(context, contact_method)
    warnings = _warnings(context, facts, contact)

    chosen = facts[: templates.facts_per_length(length)]
    availability = _availability_fact(contact)
    facts_used = [fact.label for fact in chosen]
    facts_available = [fact.label for fact in facts]
    if availability is not None:
        facts_used.append(availability.label)
        facts_available.append(availability.label)

    if config.enabled and backend is not None and backend.available():
        draft = _llm_draft(
            context,
            backend,
            style=style,
            length=length,
            contact=contact,
            config=config,
        )
        if draft is not None:
            ok, issues = validate_llm_message(
                draft,
                context,
                facts,
                max_chars=config.max_message_chars,
            )
            if ok:
                referenced = extract_referenced_facts(draft, facts)
                used = referenced or facts_used
                return OutreachDraft(
                    message=sanitize_text(draft),
                    style=style,
                    length=length,
                    mode="llm",
                    contact_method=contact[0] if contact else None,
                    contact_target=contact[1] if contact else None,
                    facts_used=used,
                    facts_available=facts_available,
                    warnings=warnings,
                )
            warnings.append("LLM draft failed grounding checks; using a template.")
        else:
            warnings.append("No local LLM response; using a template draft.")

    message = compose_message(
        context,
        style=style,
        length=length,
        facts=chosen,
        max_chars=config.max_message_chars,
    )
    ok, issues = validate_template_message(
        message, context, facts_used, facts_available, max_chars=config.max_message_chars
    )
    return OutreachDraft(
        message=message,
        style=style,
        length=length,
        mode="template",
        contact_method=contact[0] if contact else None,
        contact_target=contact[1] if contact else None,
        facts_used=facts_used,
        facts_available=facts_available,
        warnings=warnings,
        valid=ok,
        issues=tuple(issues),
    )


def _availability_fact(
    contact: Optional[Tuple[str, str]],
) -> Optional[Fact]:
    if not contact:
        return None
    method, _target = contact
    return Fact(
        key=f"availability_{method}",
        label=_AVAILABILITY_LABELS.get(method, method),
        phrase=_AVAILABILITY_PHRASES.get(method, method),
    )


def _warnings(
    context: Mapping[str, Any],
    facts: Sequence[Fact],
    contact: Optional[Tuple[str, str]],
) -> list[str]:
    warnings: list[str] = []
    contact_dict = context.get("contact") or {}
    if not contact_dict.get("owner_name"):
        warnings.append("No owner name stored — using the business name.")
    if contact is None:
        warnings.append("No direct contact method is available for this lead.")
    if not facts:
        warnings.append("No specific findings detected — the message stays generic.")
    elif len(facts) < 3:
        warnings.append("Only a few specific findings were detected.")
    if not context.get("seo"):
        warnings.append("No SEO audit stored for this lead.")
    if not context.get("visual"):
        warnings.append("No visual audit stored for this lead.")
    if not context.get("top_opportunities"):
        warnings.append("No business opportunities detected.")
    return warnings


def _llm_draft(
    context: Mapping[str, Any],
    backend: LLMBackend,
    *,
    style: str,
    length: str,
    contact: Optional[Tuple[str, str]],
    config: OutreachConfig,
) -> Optional[str]:
    system_prompt = (
        "You write short, personalized outreach messages for small local businesses.\n"
        "Hard rules:\n"
        "- Use only the facts inside the <lead_data> block. Never invent business "
        "details, owner names, services, technologies, scores, SEO or visual issues.\n"
        "- Never claim improvements that were not detected in the supplied facts.\n"
        "- Do not exaggerate and do not invent contact methods.\n"
        "- Reference the business and at least one real finding from the facts.\n"
        "- Keep it concise, natural and human. No placeholder tokens like "
        "{business_name}."
    )
    context_text = outreach_context_text(context)[: int(config.max_context_chars)]
    if contact:
        method_label = CONTACT_LABELS.get(contact[0], contact[0])
        contact_line = f"{method_label} ({contact[1]})"
    else:
        contact_line = "none — no direct contact method is available"
    user_prompt = (
        f"Style: {style}\n"
        f"Length: {length}\n"
        f"Contact method: {contact_line}\n\n"
        "Write the outreach message using ONLY the facts below.\n"
        + fenced_data([context_text])
    )
    return backend.synthesize(system_prompt, user_prompt)