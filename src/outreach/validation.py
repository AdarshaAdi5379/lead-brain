from __future__ import annotations

import re
from typing import Any, Mapping, Optional, Sequence

# Grounding + hygiene checks for generated outreach.
#
# Rules: a generated message may only reference facts that were actually
# collected, may not invent owner names, must be grounded (name the business
# or a real finding), and must be free of control characters, leftovers and
# runaway length. Like the chat grounding guard, this is a deterministic
# post-check -- the generator also constrains the model in its prompt.

_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_PLACEHOLDER_RE = re.compile(r"\{[a-z_]+\}")
_QUOTED_NAME_RE = re.compile(r'"([^"]{2,80})"')

_DEFAULT_MAX_CHARS = 8000


def _clean(text: str) -> str:
    return str(text or "").strip()


def _has_control_chars(text: str) -> bool:
    return bool(_CONTROL_RE.search(text))


def validate_template_message(
    message: str,
    context: Mapping[str, Any],
    facts_used: Sequence[str],
    facts_available: Sequence[str],
    max_chars: int = _DEFAULT_MAX_CHARS,
) -> tuple[bool, list[str]]:
    """Check a template-composed message (facts must be chosen from available)."""
    issues: list[str] = []
    message = _clean(message)
    if not message:
        issues.append("Message is empty.")
    if _has_control_chars(message):
        issues.append("Message contains control characters.")
    if len(message) > int(max_chars):
        issues.append("Message exceeds the maximum length.")
    if _PLACEHOLDER_RE.search(message):
        issues.append("Message contains an unrendered placeholder.")
    known = {str(label).strip().lower() for label in facts_available if label}
    for label in facts_used:
        if str(label).strip().lower() not in known:
            issues.append(f"Message references an unavailable fact: {label}.")
    return (not issues, issues)


def validate_llm_message(
    message: str,
    context: Mapping[str, Any],
    facts: Sequence[Any],
    max_chars: int = _DEFAULT_MAX_CHARS,
) -> tuple[bool, list[str]]:
    """Check an LLM draft before it is shown to the user.

    * must be non-empty, control-character-free, within length bounds;
    * any quoted name it invents must match the stored owner/business name;
    * it must be grounded: reference the business name, owner, or at least one
      collected finding.
    """
    issues: list[str] = []
    message = _clean(message)
    if not message:
        issues.append("LLM draft is empty.")
    if _has_control_chars(message):
        issues.append("LLM draft contains control characters.")
    if len(message) > int(max_chars):
        issues.append("LLM draft exceeds the maximum length.")

    business = context.get("business") or {}
    contact = context.get("contact") or {}
    allowed = [
        str(business.get("business_name") or "").strip(),
        str(contact.get("owner_name") or "").strip(),
    ]
    allowed = [name for name in allowed if name]

    quoted = [name for name in _QUOTED_NAME_RE.findall(message) if name.strip()]
    lowered_allowed = [name.lower() for name in allowed]
    for name in quoted:
        lowered = name.strip().lower()
        if not any(lowered in allowed_l or allowed_l in lowered for allowed_l in lowered_allowed):
            issues.append(f"LLM draft references an unknown name: {name}.")

    if not issues:
        terms: list[str] = []
        terms += [name.lower() for name in allowed]
        terms += [
            str(getattr(fact, "label", "") or "").lower() for fact in facts
        ]
        terms += [
            str(getattr(fact, "phrase", "") or "").lower() for fact in facts
        ]
        messages = message.lower()
        if not any(term and term in messages for term in terms):
            issues.append("LLM draft is not grounded in the supplied facts.")
    return (not issues, issues)


def extract_referenced_facts(
    message: str, facts: Sequence[Any]
) -> list[str]:
    """Which fact labels are visibly referenced in a draft (best-effort)."""
    haystack = _clean(message).lower()
    if not haystack:
        return []
    referenced: list[str] = []
    for fact in facts:
        label = str(getattr(fact, "label", "") or "").strip()
        phrase = str(getattr(fact, "phrase", "") or "").strip()
        if not label:
            continue
        if (label.lower() in haystack) or (phrase and phrase.lower() in haystack):
            if label not in referenced:
                referenced.append(label)
    return referenced


def validate_text_safety(
    text: str, *, max_chars: int = _DEFAULT_MAX_CHARS
) -> bool:
    """True when a piece of text is safe to store/render."""
    if not text:
        return False
    text = _clean(text)
    if not text:
        return False
    if _has_control_chars(text):
        return False
    if len(text) > int(max_chars):
        return False
    return True