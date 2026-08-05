from __future__ import annotations

import abc
import json
import logging
import time
import urllib.error
import urllib.request
from typing import Any, Optional

from src.chat.config import ChatConfig
from src.chat.safety import redact

logger = logging.getLogger("lead.chat.llm")

# Local LLM backends for RAG synthesis. stdlib urllib only — no extra deps.
# Backends never raise; every failure degrades to None so the assistant falls
# back to the deterministic retrieval summary mode. Availability is probed on
# a short timeout and cached briefly. Only localhost endpoints are contacted
# unless the user explicitly overrides the base URL in settings.

_AVAILABILITY_TTL_S = 30.0
_PROBE_TIMEOUT_S = 3.0


class LLMBackend(abc.ABC):
    """Abstract local-text-generation backend."""

    @property
    @abc.abstractmethod
    def name(self) -> str:
        ...

    @abc.abstractmethod
    def available(self) -> bool:
        ...

    @abc.abstractmethod
    def synthesize(self, system_prompt: str, user_prompt: str) -> Optional[str]:
        ...


class _HttpBackend(LLMBackend):
    """Shared HTTP plumbing: availability probe + chat completion POST."""

    def __init__(self, *, base_url: str, model: str, api_key: str = "", timeout_s: int = 60):
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._api_key = api_key
        self._timeout_s = timeout_s
        self._available: Optional[bool] = None
        self._checked_at = 0.0

    def _probe_endpoint(self) -> Optional[str]:
        raise NotImplementedError

    def _chat_endpoint(self) -> str:
        raise NotImplementedError

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return headers

    def available(self) -> bool:
        now = time.monotonic()
        if self._available is not None and now - self._checked_at < _AVAILABILITY_TTL_S:
            return self._available
        url = self._probe_endpoint()
        self._available = bool(url and _http_get(url, timeout=_PROBE_TIMEOUT_S))
        self._checked_at = now
        return self._available

    def synthesize(self, system_prompt: str, user_prompt: str) -> Optional[str]:
        if not self.available():
            return None
        payload = self._chat_payload(system_prompt, user_prompt)
        try:
            data = _http_post_json(self._chat_endpoint(), payload, self._headers(), self._timeout_s)
        except Exception as exc:
            logger.debug("LLM synthesis failed for %s: %s", self.name, redact(str(exc)))
            return None
        return self._extract_text(data)

    def _chat_payload(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        raise NotImplementedError

    def _extract_text(self, data: Any) -> Optional[str]:
        raise NotImplementedError


class OllamaBackend(_HttpBackend):
    """Native Ollama backend (POST {base}/api/chat, stream=false)."""

    @property
    def name(self) -> str:
        return "ollama"

    def _probe_endpoint(self) -> str:
        return f"{self._base_url}/api/tags"

    def _chat_endpoint(self) -> str:
        return f"{self._base_url}/api/chat"

    def _chat_payload(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        return {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "stream": False,
        }

    def _extract_text(self, data: Any) -> Optional[str]:
        if not isinstance(data, dict):
            return None
        message = data.get("message")
        if isinstance(message, dict) and isinstance(message.get("content"), str):
            return message["content"].strip()
        return None


class OpenAICompatibleBackend(_HttpBackend):
    """Generic /v1/chat/completions client (llama.cpp, LM Studio, ...)."""

    @property
    def name(self) -> str:
        return "openai-compatible"

    def _probe_endpoint(self) -> str:
        return f"{self._base_url}/models"

    def _chat_endpoint(self) -> str:
        return f"{self._base_url}/chat/completions"

    def _chat_payload(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        return {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.0,
        }

    def _extract_text(self, data: Any) -> Optional[str]:
        if not isinstance(data, dict):
            return None
        choices = data.get("choices")
        if isinstance(choices, list) and choices:
            message = choices[0].get("message")
            if isinstance(message, dict) and isinstance(message.get("content"), str):
                return message["content"].strip()
        return None


class NoLLMBackend(LLMBackend):
    """No synthesis available — retrieval summary mode only."""

    @property
    def name(self) -> str:
        return "none"

    def available(self) -> bool:
        return False

    def synthesize(self, system_prompt: str, user_prompt: str) -> Optional[str]:
        return None


def get_backend(config: ChatConfig) -> LLMBackend:
    """Resolve the configured synthesis backend (never raises)."""
    mode = (config.llm_backend or "auto").strip().lower()
    if mode == "none":
        return NoLLMBackend()
    if mode == "ollama":
        return OllamaBackend(
            base_url=config.ollama_base_url,
            model=config.ollama_model,
            timeout_s=config.llm_timeout_s,
        )
    if mode == "openai":
        return OpenAICompatibleBackend(
            base_url=config.openai_compatible_base_url,
            model=config.openai_compatible_model,
            api_key=config.openai_compatible_api_key,
            timeout_s=config.llm_timeout_s,
        )

    ollama = OllamaBackend(
        base_url=config.ollama_base_url,
        model=config.ollama_model,
        timeout_s=config.llm_timeout_s,
    )
    if ollama.available():
        return ollama
    compatible = OpenAICompatibleBackend(
        base_url=config.openai_compatible_base_url,
        model=config.openai_compatible_model,
        api_key=config.openai_compatible_api_key,
        timeout_s=config.llm_timeout_s,
    )
    if compatible.available():
        return compatible
    return NoLLMBackend()


def _http_get(url: str, *, timeout: float) -> bool:
    try:
        request = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status == 200
    except Exception:
        return False


def _http_post_json(
    url: str,
    payload: dict[str, Any],
    headers: dict[str, str],
    timeout: float,
) -> Any:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers=headers,
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
            return json.loads(raw)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace") if hasattr(exc, "read") else str(exc)
        raise RuntimeError(f"HTTP {getattr(exc, 'code', 0) or 0}: {redact(body[:500])}") from exc