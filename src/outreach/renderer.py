from __future__ import annotations

import re
from typing import Any, Mapping, Sequence

from src.outreach import templates

# Pure message composition. Takes a context + chosen facts and turns the
# per-style section builders into one final message. Sanitizes control
# characters (database values are untrusted), preserves blank-line structure,
# and hard-caps the length. It never talks to storage, the network or the LLM.

_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_MULTI_BLANK_RE = re.compile(r"\n{3,}")


def compose_message(
    context: Mapping[str, Any],
    *,
    style: str,
    length: str,
    facts: Sequence[Any],
    max_chars: int = 4000,
) -> str:
    """Compose a complete outreach message for one style/length/facts set."""
    sections: list[str] = []
    if templates.has_subject(style):
        subject = templates.render_subject(style, context)
        if subject.strip():
            sections.append(f"Subject: {subject.strip()}")

    for name in templates.section_names(style, length):
        text = templates.render_section(name, context, style, facts)
        if not text.strip():
            continue
        sections.append(text.strip())

    message = "\n\n".join(sections)
    message = _MULTI_BLANK_RE.sub("\n\n", message)
    message = _CONTROL_RE.sub("", message)
    return message[: int(max_chars)]