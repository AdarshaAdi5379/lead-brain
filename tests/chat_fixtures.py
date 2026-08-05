"""Synthetic fixtures for the grounded chat assistant tests (no network, no LLM).

Reuses the rich ``SearchTestDb`` from the search fixtures (real upsert path,
SEO/visual/scores/opportunities/technologies helpers) and adds a fast
``ChatConfig`` factory plus a scripted fake LLM backend for RAG-mode tests.
"""

from __future__ import annotations

from typing import Any, Optional

from src.chat.config import ChatConfig
from src.chat.llm import LLMBackend
from tests.search_fixtures import SearchTestDb


def chat_config(**overrides: Any) -> ChatConfig:
    """Small, fast config: no synthesis backend, small retrieval limits."""
    base: dict[str, Any] = {
        "enabled": True,
        "llm_backend": "none",
        "persist_sessions": False,
        "top_k": 10,
        "max_context_leads": 8,
        "max_context_chars": 24000,
        "max_history": 10,
    }
    base.update(overrides)
    return ChatConfig(**base)


class FakeLLMBackend(LLMBackend):
    """Scripted backend: returns the canned answer whenever available."""

    name = "fake"

    def __init__(self, answer: Optional[str] = None, *, available: bool = True) -> None:
        self._answer = answer
        self._available = available
        self.calls: list[tuple[str, str]] = []

    def available(self) -> bool:
        return self._available

    def synthesize(self, system_prompt: str, user_prompt: str) -> Optional[str]:
        self.calls.append((system_prompt, user_prompt))
        return self._answer
