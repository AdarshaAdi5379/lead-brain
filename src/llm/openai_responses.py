from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Optional


@dataclass(frozen=True)
class OpenAIUsage:
    input_tokens: int
    output_tokens: int
    total_tokens: int

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> Optional["OpenAIUsage"]:
        usage = payload.get("usage")
        if not isinstance(usage, dict):
            return None

        def _as_int(value: Any) -> int:
            try:
                return int(value)
            except Exception:
                return 0

        # The API has evolved; accept a few common shapes.
        input_tokens = _as_int(usage.get("input_tokens") or usage.get("prompt_tokens"))
        output_tokens = _as_int(usage.get("output_tokens") or usage.get("completion_tokens"))
        total_tokens = _as_int(usage.get("total_tokens") or (input_tokens + output_tokens))

        if input_tokens == 0 and output_tokens == 0 and total_tokens == 0:
            return None
        return cls(input_tokens=input_tokens, output_tokens=output_tokens, total_tokens=total_tokens)


class OpenAIHTTPError(RuntimeError):
    def __init__(self, status: int, body: str) -> None:
        super().__init__(f"OpenRouter API error {status}: {body}")
        self.status = status
        self.body = body


# Error statuses that must never be retried: invalid key/auth, forbidden,
# rate limited, or a malformed request. Free OpenRouter tiers are strictly
# quota-limited, so a retry on 429 would just burn the daily allowance.
NO_RETRY_STATUSES = frozenset({400, 401, 403, 404, 429})

# Transient server-side statuses that may be retried once.
TRANSIENT_STATUSES = frozenset({500, 502, 503, 504})


def _base_url() -> str:
    return os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1").rstrip("/")


def _api_key() -> str:
    key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not key:
        raise RuntimeError("OPENROUTER_API_KEY is not set")
    return key


def _extra_headers() -> dict[str, str]:
    """Optional OpenRouter attribution headers (never required)."""
    headers: dict[str, str] = {}
    referer = os.environ.get("OPENROUTER_HTTP_REFERER", "").strip()
    title = os.environ.get("OPENROUTER_X_TITLE", "").strip()
    if referer:
        headers["HTTP-Referer"] = referer
    if title:
        headers["X-Title"] = title
    return headers


def _post_json(
    url: str,
    payload: dict[str, Any],
    *,
    timeout_s: int,
) -> dict[str, Any]:
    """POST a JSON payload with the shared OpenRouter auth headers."""
    data = json.dumps(payload).encode("utf-8")
    headers = {
        "Authorization": f"Bearer {_api_key()}",
        "Content-Type": "application/json",
    }
    headers.update(_extra_headers())
    request = urllib.request.Request(url, data=data, method="POST", headers=headers)

    try:
        with urllib.request.urlopen(request, timeout=timeout_s) as response:
            raw = response.read().decode("utf-8", errors="replace")
            return json.loads(raw)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace") if hasattr(exc, "read") else str(exc)
        raise OpenAIHTTPError(getattr(exc, "code", 0) or 0, body[:2000]) from exc


def create_response(
    *,
    model: str,
    system_prompt: str,
    user_prompt: str,
    timeout_s: int = 60,
) -> tuple[str, Optional[OpenAIUsage], dict[str, Any]]:
    """
    Minimal OpenAI-compatible Chat Completions call against OpenRouter
    (stdlib urllib). OpenRouter supports this endpoint for every model,
    including the free router.

    Returns:
      (output_text, usage, raw_payload)
    """

    url = f"{_base_url()}/chat/completions"
    payload: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }
    parsed = _post_json(url, payload, timeout_s=timeout_s)

    output_text = _extract_output_text(parsed)
    usage = OpenAIUsage.from_payload(parsed)
    return output_text, usage, parsed


def _extract_output_text(payload: dict[str, Any]) -> str:
    """
    Best-effort extraction of the model's text output from a
    Chat Completions payload.
    """

    choices = payload.get("choices")
    if isinstance(choices, list):
        parts: list[str] = []
        for choice in choices:
            if not isinstance(choice, dict):
                continue
            message = choice.get("message")
            if not isinstance(message, dict):
                continue
            content = message.get("content")
            if isinstance(content, str) and content.strip():
                parts.append(content)
            elif isinstance(content, list):
                # Tool-style / multimodal replies with text parts.
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        text = block.get("text")
                        if isinstance(text, str):
                            parts.append(text)
        if parts:
            return "\n".join(parts).strip()

    # Fallbacks seen in older clients / wrappers.
    for key in ("output_text", "text", "content"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    return ""


def create_vision_response(
    *,
    images: list[str],
    model: str,
    prompt: str,
    system_prompt: str = "",
    max_tokens: int = 400,
    timeout_s: int = 90,
) -> dict[str, Any]:
    """
    Minimal multimodal call against the OpenRouter Chat Completions endpoint
    (stdlib urllib).

    ``images`` are base64-encoded JPEG data URLs. The model's output is parsed
    as strict JSON and returned as a dict; unparseable output yields an empty
    dict so callers can degrade gracefully.
    """
    user_content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
    for encoded in images:
        user_content.append(
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{encoded}"}}
        )

    messages: list[dict[str, Any]] = [{"role": "user", "content": user_content}]
    if system_prompt.strip():
        messages.insert(
            0,
            {"role": "system", "content": system_prompt},
        )

    url = f"{_base_url()}/chat/completions"
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "max_tokens": int(max_tokens),
        "temperature": 0.2,
    }
    parsed = _post_json(url, payload, timeout_s=timeout_s)

    output_text = _extract_output_text(parsed)
    if not output_text.strip():
        return {}
    try:
        value = json.loads(output_text)
        return value if isinstance(value, dict) else {}
    except ValueError:
        return {}