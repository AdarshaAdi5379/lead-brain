from __future__ import annotations

import json
import sqlite3
from typing import Any, Optional

# Persistence primitives for the grounded chat assistant (chat_sessions +
# chat_messages). Lightweight and optional: when CHAT_PERSIST_SESSIONS is off
# the chat works purely in-memory and these helpers are simply never called.
# All SQL is parameterized; no user-supplied text ever reaches a query string.


def create_session(connection: sqlite3.Connection, session_id: str) -> None:
    """Insert a chat session row (no-op when the id already exists)."""
    connection.execute(
        "INSERT OR IGNORE INTO chat_sessions (session_id) VALUES (?)",
        (str(session_id),),
    )
    connection.commit()


def touch_session(connection: sqlite3.Connection, session_id: str) -> None:
    """Refresh a session's updated_at timestamp."""
    connection.execute(
        "UPDATE chat_sessions SET updated_at = datetime('now') WHERE session_id = ?",
        (str(session_id),),
    )
    connection.commit()


def append_message(
    connection: sqlite3.Connection,
    *,
    session_id: str,
    role: str,
    message: str,
    retrieved_lead_ids: Optional[list[int]] = None,
    intent: Optional[str] = None,
) -> int:
    """Persist one chat message; returns its row id."""
    cursor = connection.execute(
        """
        INSERT INTO chat_messages (
          session_id, role, message, retrieved_lead_ids_json, intent
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            str(session_id),
            role,
            message,
            json.dumps([int(i) for i in (retrieved_lead_ids or [])], separators=(",", ":")),
            intent,
        ),
    )
    connection.commit()
    return int(cursor.lastrowid)


def messages_for_session(
    connection: sqlite3.Connection,
    session_id: str,
    *,
    limit: Optional[int] = None,
) -> list[dict[str, Any]]:
    """Decoded messages for a session, oldest first (None when absent)."""
    sql = "SELECT * FROM chat_messages WHERE session_id = ? ORDER BY id"
    params: list[Any] = [str(session_id)]
    if limit is not None:
        sql += " DESC LIMIT ?"
        params.append(int(limit))
        rows = connection.execute(sql, params).fetchall()
        rows = list(reversed(rows))
    else:
        rows = connection.execute(sql, params).fetchall()
    return [_decode_message(row) for row in rows]


def delete_session(connection: sqlite3.Connection, session_id: str) -> int:
    """Remove a session and its messages; returns the message count removed."""
    cursor = connection.execute(
        "DELETE FROM chat_messages WHERE session_id = ?", (str(session_id),)
    )
    deleted_messages = cursor.rowcount
    connection.execute(
        "DELETE FROM chat_sessions WHERE session_id = ?", (str(session_id),)
    )
    connection.commit()
    return int(deleted_messages)


def last_session_id(connection: sqlite3.Connection) -> Optional[str]:
    """Most recently touched session id (for restoring the last conversation)."""
    row = connection.execute(
        "SELECT session_id FROM chat_sessions ORDER BY updated_at DESC LIMIT 1"
    ).fetchone()
    return str(row[0]) if row is not None else None


def _decode_message(row: sqlite3.Row) -> dict[str, Any]:
    record = dict(row)
    raw = record.get("retrieved_lead_ids_json")
    try:
        record["retrieved_lead_ids"] = [int(i) for i in json.loads(raw or "[]")]
    except (ValueError, TypeError):
        record["retrieved_lead_ids"] = []
    return record
