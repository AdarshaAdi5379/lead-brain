from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import src.settings as settings_module

# Tunables for the grounded chat assistant. Every knob lives here (or in the
# environment-backed settings module) — no magic numbers in engine code.


@dataclass(frozen=True)
class ChatConfig:
    """Configuration for the local chat assistant (mirrors Visual/SearchConfig)."""

    # Master switch: when off, the chat page is unavailable.
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
    # Context budget for retrieval-based answers.
    max_context_leads: int = 8
    max_context_chars: int = 24000
    # Conversation history kept per session (most recent turns).
    max_history: int = 10
    # When on, chat sessions/messages persist in SQLite.
    persist_sessions: bool = True
    # Default number of leads retrieved per question.
    top_k: int = 15

    @property
    def backend_name(self) -> str:
        return self.llm_backend


def from_settings(module: Any = settings_module) -> ChatConfig:
    """Build a ChatConfig from the environment-backed settings module."""
    return ChatConfig(
        enabled=bool(getattr(module, "CHAT_ENABLED", True)),
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
        max_context_leads=int(getattr(module, "CHAT_MAX_CONTEXT_LEADS", 8)),
        max_context_chars=int(getattr(module, "CHAT_MAX_CONTEXT_CHARS", 24000)),
        max_history=int(getattr(module, "CHAT_MAX_HISTORY", 10)),
        persist_sessions=bool(getattr(module, "CHAT_PERSIST_SESSIONS", True)),
        top_k=int(getattr(module, "CHAT_TOP_K", 15)),
    )
