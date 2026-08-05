from __future__ import annotations

import logging
import sqlite3
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from src.chat.config import ChatConfig
from src.storage import chat as chat_storage
from src.storage.db import connect, init_db

logger = logging.getLogger("lead.chat.memory")

# Lightweight per-session conversation memory. Keeps the most recent turns in
# memory for prompt context and optionally mirrors them into SQLite
# (chat_sessions / chat_messages) so history survives dashboard restarts.


@dataclass(frozen=True)
class ChatMessage:
    role: str
    message: str
    retrieved_lead_ids: list[int] = field(default_factory=list)
    intent: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))


class ConversationMemory:
    """In-memory session history with optional SQLite persistence."""

    def __init__(self, db_path: Path, session_id: str, config: ChatConfig) -> None:
        self._db_path = Path(db_path)
        self.session_id = session_id or str(uuid.uuid4())
        self.config = config
        self._messages: deque[ChatMessage] = deque()
        if config.persist_sessions:
            self._load_persisted()

    def add(
        self,
        *,
        role: str,
        message: str,
        retrieved_lead_ids: Optional[list[int]] = None,
        intent: Optional[str] = None,
    ) -> None:
        entry = ChatMessage(
            role=role,
            message=message,
            retrieved_lead_ids=[int(i) for i in (retrieved_lead_ids or [])],
            intent=intent,
        )
        self._messages.append(entry)
        max_history = int(self.config.max_history or 0)
        if max_history > 0 and len(self._messages) > max_history:
            for _ in range(len(self._messages) - max_history):
                self._messages.popleft()
        if self.config.persist_sessions:
            try:
                with self._connection() as connection:
                    chat_storage.create_session(connection, self.session_id)
                    chat_storage.append_message(
                        connection,
                        session_id=self.session_id,
                        role=entry.role,
                        message=entry.message,
                        retrieved_lead_ids=entry.retrieved_lead_ids,
                        intent=entry.intent,
                    )
                    chat_storage.touch_session(connection, self.session_id)
            except sqlite3.Error as exc:
                logger.debug("Chat persistence failed for %s: %s", self.session_id, exc)

    def history(self) -> list[ChatMessage]:
        return list(self._messages)

    def history_text(self, *, max_turns: Optional[int] = None) -> str:
        """Render recent turns as prompt context (oldest first)."""
        turns = list(self._messages)
        if max_turns is not None and max_turns > 0:
            turns = turns[-int(max_turns):]
        parts: list[str] = []
        for message in turns:
            prefix = "USER" if message.role == "user" else "ASSISTANT"
            parts.append(f"{prefix}: {message.message}")
        return "\n".join(parts)

    def latest_lead_ids(self) -> list[int]:
        for message in reversed(self._messages):
            if message.retrieved_lead_ids:
                return list(message.retrieved_lead_ids)
        return []

    def clear(self) -> None:
        self._messages.clear()
        if self.config.persist_sessions:
            try:
                with self._connection() as connection:
                    chat_storage.delete_session(connection, self.session_id)
            except sqlite3.Error as exc:
                logger.debug("Chat clear failed for %s: %s", self.session_id, exc)

    def _load_persisted(self) -> None:
        try:
            with self._connection() as connection:
                rows = chat_storage.messages_for_session(
                    connection, self.session_id, limit=self.config.max_history
                )
        except sqlite3.Error as exc:
            logger.debug("Chat history load failed for %s: %s", self.session_id, exc)
            return
        for row in rows:
            self._messages.append(
                ChatMessage(
                    role=row.get("role") or "",
                    message=row.get("message") or "",
                    retrieved_lead_ids=list(row.get("retrieved_lead_ids") or []),
                    intent=row.get("intent"),
                    created_at=row.get("created_at") or "",
                )
            )

    @classmethod
    def new_session_id(cls) -> str:
        return str(uuid.uuid4())

    def _connection(self) -> sqlite3.Connection:
        connection = connect(self._db_path)
        init_db(connection)
        return connection