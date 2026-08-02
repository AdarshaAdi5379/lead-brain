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
        super().__init__(f"OpenAI API error {status}: {body}")
        self.status = status
        self.body = body


def _base_url() -> str:
    return os.environ.get("OPENAI_BASE_URL", "https://api.openai.com").rstrip("/")


def _api_key() -> str:
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not key:
        raise RuntimeError("OPENAI_API_KEY is not set")
    return key


def create_response(
    *,
    model: str,
    system_prompt: str,
    user_prompt: str,
    timeout_s: int = 60,
) -> tuple[str, Optional[OpenAIUsage], dict[str, Any]]:
    """
    Minimal OpenAI Responses API call using stdlib urllib.

    Returns:
      (output_text, usage, raw_payload)
    """

    url = f"{_base_url()}/v1/responses"
    payload: dict[str, Any] = {
        "model": model,
        "input": [
            {"role": "system", "content": [{"type": "input_text", "text": system_prompt}]},
            {"role": "user", "content": [{"type": "input_text", "text": user_prompt}]},
        ],
    }
    data = json.dumps(payload).encode("utf-8")

    request = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={
            "Authorization": f"Bearer {_api_key()}",
            "Content-Type": "application/json",
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout_s) as response:
            raw = response.read().decode("utf-8", errors="replace")
            parsed = json.loads(raw)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace") if hasattr(exc, "read") else str(exc)
        raise OpenAIHTTPError(getattr(exc, "code", 0) or 0, body[:2000]) from exc

    output_text = _extract_output_text(parsed)
    usage = OpenAIUsage.from_payload(parsed)
    return output_text, usage, parsed


def _extract_output_text(payload: dict[str, Any]) -> str:
    """
    Best-effort extraction of the model's text output from a Responses API payload.
    """

    output = payload.get("output")
    if isinstance(output, list):
        parts: list[str] = []
        for item in output:
            if not isinstance(item, dict):
                continue
            content = item.get("content")
            if not isinstance(content, list):
                continue
            for block in content:
                if isinstance(block, dict) and block.get("type") in {"output_text", "text"}:
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
    Minimal multimodal call against the OpenAI Responses API (stdlib urllib).

    ``images`` are base64-encoded JPEG data URLs. The model's output is parsed
    as strict JSON and returned as a dict; unparseable output yields an empty
    dict so callers can degrade gracefully.
    """
    user_content: list[dict[str, Any]] = [
        {"type": "input_text", "text": prompt},
    ]
    for encoded in images:
        user_content.append(
            {"type": "input_image", "image_url": f"data:image/jpeg;base64,{encoded}"}
        )

    input_parts: list[dict[str, Any]] = [{"role": "user", "content": user_content}]
    if system_prompt.strip():
        input_parts.insert(
            0,
            {"role": "system", "content": [{"type": "input_text", "text": system_prompt}]},
        )

    url = f"{_base_url()}/v1/responses"
    payload: dict[str, Any] = {
        "model": model,
        "input": input_parts,
        "max_output_tokens": int(max_tokens),
        "temperature": 0.2,
    }
    data = json.dumps(payload).encode("utf-8")

    request = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={
            "Authorization": f"Bearer {_api_key()}",
            "Content-Type": "application/json",
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout_s) as response:
            raw = response.read().decode("utf-8", errors="replace")
            parsed = json.loads(raw)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace") if hasattr(exc, "read") else str(exc)
        raise OpenAIHTTPError(getattr(exc, "code", 0) or 0, body[:2000]) from exc

    output_text = _extract_output_text(parsed)
    if not output_text.strip():
        return {}
    try:
        value = json.loads(output_text)
        return value if isinstance(value, dict) else {}
    except ValueError:
        return {}

