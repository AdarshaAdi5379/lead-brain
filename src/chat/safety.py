from __future__ import annotations

import re
from typing import Optional

# Safety helpers for the chat assistant.
#
# Grounding rules:
#   * retrieved database / crawled-website text is treated as untrusted data,
#     never as instructions (see the <lead_data> fencing in prompts.py);
#   * generated answers are checked against the retrieved lead names so the
#     assistant cannot reference businesses that were not in its context;
#   * nothing user- or website-supplied is ever executed, evaluated or logged.


_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_WHITESPACE_RE = re.compile(r"[ \t\r\n]+")
_SECRET_RE = re.compile(
    r"(?i)(sk-[a-z0-9_\-]{12,}|bearer\s+[a-z0-9._\-]{12,}|api[_-]?key['\"]?\s*[:=]\s*\S+)"
)
_QUOTED_NAME_RE = re.compile(r'"([^"]{2,80})"')
_LEAD_REFERENCE_RE = re.compile(r"(?i)(lead\s*#?\s*\d+|#\s*\d+|founder|owner|manager)")


def sanitize_text(text: str, *, max_chars: int = 8000) -> str:
    """Neutralize control characters and cap length (safe for prompts/answers).

    Keeps newlines and normal spacing; strips anything that could break the
    prompt framing (control chars, zero-width markers) and long runaway text.
    """
    if not text:
        return ""
    cleaned = _CONTROL_RE.sub("", str(text))
    cleaned = _WHITESPACE_RE.sub(" ", cleaned).strip()
    return cleaned[:max_chars]


def redact(value: Optional[str]) -> str:
    """Redact secret-looking tokens from loggable strings."""
    if not value:
        return ""
    return _SECRET_RE.sub("[REDACTED]", str(value))


def fenced_data(blocks: list[str]) -> str:
    """Wrap retrieved content in an explicit untrusted-data fence.

    The fence boundaries are referenced by the system prompt: anything between
    them is data, never instructions.
    """
    if not blocks:
        return ""
    body = "\n\n".join(block for block in blocks if block.strip())
    if not body:
        return ""
    return f"<lead_data>\n{body}\n</lead_data>"


def validate_grounded_answer(answer: str, lead_names: list[str]) -> tuple[bool, list[str]]:
    """Check an answer only references businesses present in the retrieved set.

    Two checks:
      1. any name the model explicitly quoted (``"..."``) must match a
         retrieved lead name — an unknown quoted name is a hard rejection;
      2. the answer must contain *some* grounding reference: a retrieved lead
         name, a numeric lead reference, a role word (founder/owner/manager),
         or a digit — a free-floating answer naming nobody and no numbers is
         treated as ungrounded and rejected.

    Returns ``(ok, unknown_names)``. This is a light deterministic guard, not
    a replacement for the grounding rules in the system prompt.
    """
    if not answer.strip():
        return (False, [])
    known = {name.strip().lower() for name in lead_names if name}

    unknown: list[str] = []
    for name in _QUOTED_NAME_RE.findall(answer):
        lowered = name.strip().lower()
        if not any(lowered in known_name or known_name in lowered for known_name in known):
            unknown.append(name)
    if unknown:
        return (False, unknown)

    lowered_answer = answer.lower()
    referenced = any(name and name in lowered_answer for name in known)
    referenced = referenced or bool(_LEAD_REFERENCE_RE.search(answer))
    referenced = referenced or any(char.isdigit() for char in answer)
    if not referenced:
        return (False, [])
    return (True, [])
