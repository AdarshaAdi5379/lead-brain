"""Tests for conversation memory (src/chat/memory.py) and its SQLite mirror."""

from __future__ import annotations

import unittest

from src.chat.memory import ConversationMemory
from tests.chat_fixtures import SearchTestDb, chat_config


class ConversationMemoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.db = SearchTestDb()
        self.config = chat_config()
        self.addCleanup(self.db.close)

    def memory(self, *, max_history: int = 10, persist: bool = False) -> ConversationMemory:
        config = chat_config(max_history=max_history, persist_sessions=persist)
        return ConversationMemory(self.db.path, "sess-1", config)

    def test_add_and_history(self) -> None:
        memory = self.memory()
        memory.add(role="user", message="hello", retrieved_lead_ids=[1, 2], intent="search")
        history = memory.history()
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0].role, "user")
        self.assertEqual(history[0].retrieved_lead_ids, [1, 2])

    def test_history_is_capped(self) -> None:
        memory = self.memory(max_history=3)
        for index in range(6):
            memory.add(role="user", message=f"turn {index}")
        self.assertEqual(len(memory.history()), 3)
        self.assertEqual(memory.history()[0].message, "turn 3")

    def test_history_text_formats_roles(self) -> None:
        memory = self.memory()
        memory.add(role="user", message="first")
        memory.add(role="assistant", message="second")
        text = memory.history_text(max_turns=2)
        self.assertIn("USER: first", text)
        self.assertIn("ASSISTANT: second", text)

    def test_history_text_respects_max_turns(self) -> None:
        memory = self.memory()
        for index in range(5):
            memory.add(role="user", message=f"turn {index}")
        text = memory.history_text(max_turns=2)
        self.assertNotIn("turn 0", text)
        self.assertIn("turn 4", text)

    def test_latest_lead_ids_scans_backwards(self) -> None:
        memory = self.memory()
        memory.add(role="user", message="first", retrieved_lead_ids=[1])
        memory.add(role="user", message="second")
        self.assertEqual(memory.latest_lead_ids(), [1])

    def test_clear_empties_memory(self) -> None:
        memory = self.memory()
        memory.add(role="user", message="hello")
        memory.clear()
        self.assertEqual(memory.history(), [])

    def test_persist_roundtrip(self) -> None:
        memory = self.memory(persist=True)
        memory.add(role="user", message="hello db", retrieved_lead_ids=[3], intent="search")
        memory.add(role="assistant", message="hi back", intent="search")
        reloaded = self.memory(persist=True)
        records = reloaded.history()
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0].message, "hello db")
        self.assertEqual(records[0].role, "user")
        self.assertEqual(records[0].retrieved_lead_ids, [3])
        self.assertEqual(records[0].intent, "search")

    def test_persist_roundtrip_respects_limit(self) -> None:
        memory = self.memory(persist=True, max_history=10)
        for index in range(5):
            memory.add(role="user", message=f"turn {index}")
        reloaded = self.memory(persist=True, max_history=3)
        loaded = [message.message for message in reloaded.history()]
        self.assertEqual(loaded, ["turn 2", "turn 3", "turn 4"])

    def test_persist_clear_removes_rows(self) -> None:
        memory = self.memory(persist=True)
        memory.add(role="user", message="hello db")
        memory.add(role="assistant", message="hi")
        memory.clear()
        reloaded = self.memory(persist=True)
        self.assertEqual(reloaded.history(), [])

    def test_unique_session_ids(self) -> None:
        ids = {ConversationMemory.new_session_id() for _ in range(100)}
        self.assertEqual(len(ids), 100)


if __name__ == "__main__":
    unittest.main()