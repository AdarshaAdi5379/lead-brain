from __future__ import annotations

from dataclasses import dataclass

from src.scraping.page_cache import content_hash


def trim_text(text: str, *, max_chars: int = 2000) -> str:
    """Cap a page's text at ``max_chars``, preferring paragraph boundaries.

    Works on line-oriented visible text (never raw HTML), so the truncation
    can never cut inside a tag. Falls back to the last space when no break is
    near the limit so words are never split."""
    text = text or ""
    max_chars = max(0, int(max_chars))
    if len(text) <= max_chars:
        return text

    head = text[:max_chars]

    # Prefer paragraph boundary ("\n\n"), then single line break, then space.
    boundary = head.rfind("\n\n")
    if boundary <= 0:
        boundary = head.rfind("\n")
    if boundary <= 0:
        boundary = head.rfind(" ")
    if boundary <= 0:
        boundary = max_chars

    trimmed = text[:boundary]
    return trimmed


@dataclass(frozen=True)
class Section:
    label: str
    url: str
    text: str


def merge_sections(sections: list[Section]) -> str:
    """Build one labelled document so the LLM knows which page each part is.

    Homepage should always be first (the caller guarantees ordering)."""
    chunks: list[str] = []
    for section in sections:
        page_url = f" {section.url}" if section.url else ""
        chunks.append("=" * 17)
        chunks.append(f"{section.label} ({section.url})".strip())
        chunks.append("=" * 17)
        chunks.append((section.text or "").strip())
    return "\n".join(chunks)


def count_chars(merged_text: str) -> int:
    return len(merged_text or "")