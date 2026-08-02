from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any, Optional

from src.extraction_schema import ExtractedLead, validate_extracted_lead
from src.llm.openai_responses import OpenAIUsage, create_response
from src.scraping.browser_fetch import FetchResult


@dataclass(frozen=True)
class ExtractionResult:
    lead: ExtractedLead
    usage: Optional[OpenAIUsage]
    raw_text: str


_EMAIL_RE = re.compile(r"\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b")
# Very forgiving; we only use this as a validator after stripping obvious noise.
_PHONE_RE = re.compile(r"^\+?[0-9().\-\s]{7,}$")


def extract_lead_from_fetch(
    fetch: FetchResult,
    *,
    model_primary: Optional[str] = None,
    model_fallback: Optional[str] = None,
    timeout_s: int = 60,
) -> ExtractionResult:
    """
    Calls an OpenAI model to extract a lead payload, then validates against ExtractedLead contract.

    Notes:
    - Expects OPENAI_API_KEY to be set.
    - Uses text-first input (visible text + small HTML snippet), not full HTML dumps.
    """

    system_prompt = _system_prompt()
    user_prompt = _user_prompt(fetch)

    model = model_primary or os.environ.get("OPENAI_MODEL_PRIMARY", "").strip() or "gpt-4.1-nano"
    fallback = (
        model_fallback or os.environ.get("OPENAI_MODEL_FALLBACK", "").strip() or "gpt-4o-mini"
    )

    try:
        output_text, usage = _call_llm(
            model=model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            fallback=fallback,
            timeout_s=timeout_s,
        )
    except Exception:
        raise

    lead = _parse_and_validate(output_text, fetch.final_url or fetch.url)
    return ExtractionResult(lead=lead, usage=usage, raw_text=output_text)


def extract_lead_from_merged_content(
    merged_text: str,
    source_url: str,
    *,
    contact_clues: Optional[list[str]] = None,
    model_primary: Optional[str] = None,
    model_fallback: Optional[str] = None,
    timeout_s: int = 60,
) -> ExtractionResult:
    """Extract a lead from the focused-crawler's merged document.

    Same schema and validation as the homepage-only path, but the model sees
    labelled sections for every crawled page instead of one page's text."""
    system_prompt = _system_prompt()
    user_prompt = _user_prompt_merged(merged_text, source_url, contact_clues or [])

    model = model_primary or os.environ.get("OPENAI_MODEL_PRIMARY", "").strip() or "gpt-4.1-nano"
    fallback = (
        model_fallback or os.environ.get("OPENAI_MODEL_FALLBACK", "").strip() or "gpt-4o-mini"
    )

    output_text, usage = _call_llm(
        model=model,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        fallback=fallback,
        timeout_s=timeout_s,
    )

    lead = _parse_and_validate(output_text, source_url)
    return ExtractionResult(lead=lead, usage=usage, raw_text=output_text)


def _call_llm(
    *,
    model: str,
    system_prompt: str,
    user_prompt: str,
    fallback: str,
    timeout_s: int,
) -> tuple[str, Optional[OpenAIUsage]]:
    try:
        output_text, usage, _raw = create_response(
            model=model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            timeout_s=timeout_s,
        )
        return output_text, usage
    except Exception:
        if fallback and fallback != model:
            output_text, usage, _raw = create_response(
                model=fallback,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                timeout_s=timeout_s,
            )
            return output_text, usage
        raise


def _system_prompt() -> str:
    return (
        "You extract structured lead info from a business website page.\n"
        "Return ONLY valid JSON (no markdown, no code fences), matching exactly this schema:\n"
        "{\n"
        '  "url": string|null,\n'
        '  "business_name": string|null,\n'
        '  "phone": string|null,\n'
        '  "email": string|null,\n'
        '  "platform": "wordpress"|"wix"|"squarespace"|"weebly"|"shopify"|"custom_html"|"custom_react"|"unknown",\n'
        '  "complexity": "basic"|"medium"|"complex"|"unknown",\n'
        '  "load_speed": "fast"|"medium"|"slow"|"unknown",\n'
        '  "extraction_success": boolean,\n'
        '  "last_error": string|null\n'
        "}\n"
        "Rules:\n"
        "- Use null for missing values.\n"
        "- Enums must be lowercase.\n"
        "- If content is blocked/empty, set extraction_success=false and provide last_error.\n"
    )


def _user_prompt(fetch: FetchResult) -> str:
    text = (fetch.text or "").strip()
    html = (fetch.html or "").strip()

    # Keep prompts bounded even if caps are changed elsewhere.
    text = text[:90_000]
    html_snippet = _extract_contact_html_snippet(html, max_chars=20_000)

    return (
        f"Target URL: {fetch.final_url or fetch.url}\n"
        f"Fetch success: {fetch.success}\n"
        f"HTTP status: {fetch.status}\n"
        f"Fetcher error (if any): {fetch.error}\n\n"
        "Visible text (may be truncated):\n"
        f"{text}\n\n"
        "HTML contact snippet (may be truncated):\n"
        f"{html_snippet}\n"
    )


def _user_prompt_merged(
    merged_text: str,
    source_url: str,
    contact_clues: list[str],
) -> str:
    merged = (merged_text or "").strip()[:90_000]
    clues = "\n".join(contact_clues) if contact_clues else "None"

    return (
        f"Target URL: {source_url}\n"
        "Content type: focused multi-page crawl of the business website\n"
        "Sections are labelled with the page they came from (HOME, ABOUT, "
        "SERVICES, ...). Boilerplate (menus, footers, cookie banners) has been "
        "removed and long pages were trimmed.\n\n"
        "Merged visible text from all crawled pages (may be truncated):\n"
        f"{merged}\n\n"
        "Contact details found on the site:\n"
        f"{clues}\n"
    )


def _extract_contact_html_snippet(html: str, *, max_chars: int) -> str:
    if not html:
        return ""

    patterns = [
        r"mailto:[^\"'>\s]+",
        r"tel:[^\"'>\s]+",
        r"contact",
        r"footer",
        r"address",
    ]
    hits: list[tuple[int, int]] = []
    lowered = html.lower()
    for pattern in patterns:
        for match in re.finditer(pattern, lowered):
            start = max(0, match.start() - 250)
            end = min(len(html), match.end() + 250)
            hits.append((start, end))
            if len(hits) >= 10:
                break
        if len(hits) >= 10:
            break

    if not hits:
        return html[:max_chars]

    # Merge overlapping windows.
    hits.sort()
    merged: list[tuple[int, int]] = []
    for start, end in hits:
        if not merged or start > merged[-1][1]:
            merged.append((start, end))
        else:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))

    snippet_parts = [html[s:e] for s, e in merged]
    snippet = "\n...\n".join(snippet_parts)
    return snippet[:max_chars]


def _parse_and_validate(output_text: str, url: str) -> ExtractedLead:
    payload = _parse_json_object(output_text)

    # Ensure required key exists even if the model forgets.
    if "url" not in payload:
        payload["url"] = url

    payload["email"] = _sanitize_email(payload.get("email"))
    payload["phone"] = _sanitize_phone(payload.get("phone"))

    try:
        return validate_extracted_lead(payload)
    except Exception as exc:
        # Surface a consistent failure payload for the pipeline.
        return validate_extracted_lead(
            {
                "url": url,
                "business_name": None,
                "phone": None,
                "email": None,
                "platform": "unknown",
                "complexity": "unknown",
                "load_speed": "unknown",
                "extraction_success": False,
                "last_error": f"Invalid extraction JSON: {exc}",
            }
        )


def _parse_json_object(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if not cleaned:
        raise ValueError("Empty model output")

    # Strip common wrappers.
    cleaned = cleaned.replace("\ufeff", "").strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned).strip()

    # Try direct parse first.
    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass

    # Fallback: extract the first {...} block.
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("No JSON object found in model output")

    candidate = cleaned[start : end + 1]
    parsed = json.loads(candidate)
    if not isinstance(parsed, dict):
        raise ValueError("Model output JSON was not an object")
    return parsed


def _sanitize_email(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None

    match = _EMAIL_RE.search(text)
    return match.group(0) if match else None


def _sanitize_phone(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None

    # Remove common label prefixes and keep the core.
    text = re.sub(r"(?i)\b(phone|tel|call)\b[:\s]*", "", text).strip()
    if not _PHONE_RE.match(text):
        return None

    # Normalize whitespace.
    return re.sub(r"\s+", " ", text)

