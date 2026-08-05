from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import src.settings as settings_module
from src.chat.config import ChatConfig

# Outreach configuration: knobs for the grounded outreach generation engine.
#
# LLM synthesis reuses the chat assistant's local text-generation settings
# (CHAT_LLM_BACKEND / CHAT_OLLAMA_* / CHAT_OPENAI_COMPATIBLE_*) so there is a
# single source of truth for local LLM availability. Template mode needs no
# LLM and always works. Every knob lives here or in the environment-backed
# settings module -- no magic numbers in engine code.


@dataclass(frozen=True)
class OutreachConfig:
    """Configuration for the outreach engine (mirrors ChatConfig).

    ``llm_backend`` and the endpoint knobs are resolved from the *chat* env
    settings, so outreach and chat share the same local backend.
    """

    # Master switch: when off, only template drafts are ever generated.
    enabled: bool = True
    # Synthesis backend: "auto" | "ollama" | "openai" | "none".
    llm_backend: str = "auto"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.2"
    openai_compatible_base_url: str = "http://localhost:1234/v1"
    openai_compatible_model: str = "local-model"
    openai_compatible_api_key: str = ""
    # Timeout for one synthesis call (seconds).
    llm_timeout_s: int = 60
    # Defaults for the dashboard selectors.
    default_style: str = "professional"
    default_length: str = "medium"
    # Hard cap on a generated message.
    max_message_chars: int = 4000
    # Cap on the outreach context text handed to an LLM (safety + cost bound).
    max_context_chars: int = 24000

    @property
    def backend_name(self) -> str:
        return self.llm_backend

    def to_chat_config(self) -> ChatConfig:
        """Build a ChatConfig that reuses the chat LLM backend machinery."""
        return ChatConfig(
            enabled=bool(self.enabled),
            llm_backend=self.llm_backend,
            ollama_base_url=self.ollama_base_url,
            ollama_model=self.ollama_model,
            openai_compatible_base_url=self.openai_compatible_base_url,
            openai_compatible_model=self.openai_compatible_model,
            openai_compatible_api_key=self.openai_compatible_api_key,
            llm_timeout_s=self.llm_timeout_s,
        )


def from_settings(module: Any = settings_module) -> OutreachConfig:
    """Build an OutreachConfig from the environment-backed settings module."""
    return OutreachConfig(
        enabled=bool(getattr(module, "OUTREACH_ENABLED", True)),
        llm_backend=str(getattr(module, "CHAT_LLM_BACKEND", "auto")).strip().lower(),
        ollama_base_url=str(
            getattr(module, "CHAT_OLLAMA_BASE_URL", "http://localhost:11434")
        ).rstrip("/"),
        ollama_model=str(getattr(module, "CHAT_OLLAMA_MODEL", "llama3.2")),
        openai_compatible_base_url=str(
            getattr(module, "CHAT_OPENAI_COMPATIBLE_BASE_URL", "http://localhost:1234/v1")
        ).rstrip("/"),
        openai_compatible_model=str(
            getattr(module, "CHAT_OPENAI_COMPATIBLE_MODEL", "local-model")
        ),
        openai_compatible_api_key=str(
            getattr(module, "CHAT_OPENAI_COMPATIBLE_API_KEY", "") or ""
        ),
        llm_timeout_s=int(getattr(module, "CHAT_LLM_TIMEOUT_S", 60)),
        default_style=str(getattr(module, "OUTREACH_DEFAULT_STYLE", "professional")),
        default_length=str(getattr(module, "OUTREACH_DEFAULT_LENGTH", "medium")),
        max_message_chars=int(getattr(module, "OUTREACH_MAX_MESSAGE_CHARS", 4000)),
        max_context_chars=int(getattr(module, "OUTREACH_MAX_CONTEXT_CHARS", 24000)),
    )