from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

from src.chat.base import ChatResponse, Intent, IntentRoute, RetrievalStrategy, RetrievedContext
from src.chat.config import ChatConfig, from_settings
from src.chat.memory import ConversationMemory
from src.chat.response import ResponseGenerator, make_backend
from src.chat.retriever import LeadRetriever

logger = logging.getLogger("lead.chat.service")

# Public service layer for the chat assistant. The dashboard calls these
# methods instead of touching storage or search directly. Everything is
# best-effort: ask() never raises — failures degrade to a no-data response.


class ChatService:
    """Grounded chat assistant over the lead intelligence database."""

    def __init__(
        self,
        db_path: Path,
        config: Optional[ChatConfig] = None,
    ) -> None:
        self._db_path = Path(db_path)
        self.config = config or from_settings()
        self.retriever = LeadRetriever(self._db_path, self.config)
        self._backend = make_backend(self.config)
        self._generator = ResponseGenerator(self._backend, self.config)

    # -- public API ----------------------------------------------------------

    def ask(
        self,
        query: str,
        *,
        session_id: Optional[str] = None,
        filters: Optional[dict[str, Any]] = None,
        lead_id: Optional[int] = None,
    ) -> ChatResponse:
        """Answer one question: route -> retrieve -> generate -> remember."""
        query = (query or "").strip()
        if not query:
            return self._empty_response("Please type a question first.")
        if not self.config.enabled:
            return self._empty_response("The chat assistant is disabled (CHAT_ENABLED=0).")

        route = self._route_for(query, lead_id=lead_id)
        memory = self._memory(session_id)
        try:
            context = self.retriever.retrieve(route, filters=filters)
        except Exception as exc:
            logger.debug("Retrieval failed for %r: %s", query, exc)
            return self._empty_response(
                "Retrieval failed for this question; please try a different wording."
            )

        response = self._generator.generate(route, context, memory=memory)

        memory.add(
            role="user",
            message=query,
            retrieved_lead_ids=response.retrieved_lead_ids,
            intent=response.intent.value,
        )
        memory.add(
            role="assistant",
            message=response.answer,
            retrieved_lead_ids=response.retrieved_lead_ids,
            intent=response.intent.value,
        )
        return response

    def retrieve_context(
        self,
        query: str,
        *,
        filters: Optional[dict[str, Any]] = None,
    ) -> RetrievedContext:
        """Expose the raw retrieval step (route + fetch) without generation."""
        route = self._route_for(query)
        return self.retriever.retrieve(route, filters=filters)

    def summarize_lead(self, lead_id: int) -> ChatResponse:
        return self._respond_for_ids(
            [lead_id],
            strategy=RetrievalStrategy.LEAD_DETAIL,
            intent=Intent.DETAIL,
            query=f"lead detail #{lead_id}",
        )

    def find_similar(self, lead_id: int, top_k: int = 10) -> ChatResponse:
        context = self.retriever.similar(lead_id, top_k=top_k)
        return self._generator.generate(
            IntentRoute(intent=Intent.SIMILAR, raw_query=f"similar to lead #{lead_id}"),
            context,
        )

    def compare(self, lead_ids: list[int]) -> ChatResponse:
        return self._respond_for_ids(
            list(lead_ids),
            strategy=RetrievalStrategy.COMPARE,
            intent=Intent.COMPARE,
            query=f"compare leads {lead_ids}",
        )

    def explain_ranking(self, lead_ids: list[int]) -> ChatResponse:
        """Explain why specific leads rank as they do (scores + rationale)."""
        context = self.retriever.context_for_lead_ids(
            list(lead_ids), strategy=RetrievalStrategy.COMPARE, query="ranking explanation"
        )
        return self._generator.generate(
            IntentRoute(intent=Intent.EXPLAIN, raw_query="explain ranking"),
            context,
        )

    def new_session(self) -> str:
        return ConversationMemory.new_session_id()

    def last_session(self) -> Optional[str]:
        """Most recently touched session id, for restoring the last conversation."""
        try:
            from src.storage.chat import last_session_id
            from src.storage.db import connect

            with connect(self._db_path) as connection:
                return last_session_id(connection)
        except Exception as exc:
            logger.debug("Could not look up last session: %s", exc)
            return None

    def load_history(self, session_id: str) -> list[dict[str, Any]]:
        """Decoded persisted turns for a session, as {role, content, ...} dicts."""
        try:
            memory = self._memory(session_id)
            history: list[dict[str, Any]] = []
            for record in memory.history():
                history.append(
                    {
                        "role": record.role,
                        "content": record.message,
                        "intent": record.intent,
                    }
                )
            return history
        except Exception as exc:
            logger.debug("Could not load history for %s: %s", session_id, exc)
            return []

    def clear_session(self, session_id: str) -> None:
        """Delete a session and its persisted messages."""
        try:
            from src.storage.chat import delete_session
            from src.storage.db import connect

            with connect(self._db_path) as connection:
                delete_session(connection, session_id)
        except Exception as exc:
            logger.debug("Could not clear session %s: %s", session_id, exc)

    def backend_status(self) -> dict[str, Any]:
        """Backend identity for the dashboard mode badge."""
        try:
            available = self._backend.available()
        except Exception:
            available = False
        return {
            "available": available,
            "name": self._backend.name,
            "mode": "rag" if available else "retrieval_summary",
        }

    # -- internals -----------------------------------------------------------

    def _respond_for_ids(
        self,
        lead_ids: list[int],
        *,
        strategy: RetrievalStrategy,
        intent: Intent,
        query: str,
    ) -> ChatResponse:
        context = self.retriever.context_for_lead_ids(lead_ids, strategy=strategy, query=query)
        return self._generator.generate(IntentRoute(intent=intent, raw_query=query), context)

    def _route_for(self, query: str, *, lead_id: Optional[int] = None) -> IntentRoute:
        route = self.retriever.route(query)
        if lead_id is not None and lead_id > 0:
            route = route.with_params(lead_id=int(lead_id))
        return route

    def _memory(self, session_id: Optional[str]) -> ConversationMemory:
        return ConversationMemory(
            self._db_path, session_id or ConversationMemory.new_session_id(), self.config
        )

    def _empty_response(self, message: str) -> ChatResponse:
        return ChatResponse(answer=message, grounded=True)


# The assistant role is covered by ChatService; keep the friendlier alias so
# callers can write ``ChatAssistant(...)`` and the name is stable.
ChatAssistant = ChatService