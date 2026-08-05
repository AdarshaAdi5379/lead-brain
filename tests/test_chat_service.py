"""Tests for the chat service facade and end-to-end ask() (src/chat/service.py)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.chat.base import ChatMode, Intent
from src.chat.service import ChatService
from tests.chat_fixtures import FakeLLMBackend, SearchTestDb, chat_config


class ChatServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.db = SearchTestDb()
        self.pizzeria = self.db.add_lead(
            name="Joe's Pizzeria", website="https://joes.example.com",
            category="Restaurant", city="Austin", platform="wordpress", priority="Hot",
        )
        self.bella = self.db.add_lead(
            name="Bella Trattoria", website="https://bella.example.org",
            category="Restaurant", city="Austin", platform="wordpress", priority="Warm",
        )
        self.plumber = self.db.add_lead(
            name="Fix-It Plumbing", category="Plumber", city="Dallas",
        )
        self.db.add_score(self.pizzeria, final_score=81, priority_label="Hot")
        self.db.add_score(self.bella, final_score=42, priority_label="Warm")
        self.db.add_seo(self.pizzeria, site_score=35, overall_health="poor")
        self.db.add_seo(self.bella, site_score=88, overall_health="good")
        self.db.add_visual(self.pizzeria, visual_score=40)
        self.db.add_opportunity(self.pizzeria, label="Website redesign", score=80)
        self.addCleanup(self.db.close)

    def service(self, **overrides) -> ChatService:
        return ChatService(self.db.path, config=chat_config(**overrides))

    def set_rag(self, service: ChatService, answer) -> None:
        service._generator.backend = FakeLLMBackend(answer)

    def test_no_data_for_empty_query(self) -> None:
        response = self.service().ask("   ")
        self.assertEqual(response.mode, ChatMode.NO_DATA)
        self.assertIn("Please type a question", response.answer)

    def test_disabled_config_short_circuits(self) -> None:
        response = self.service(enabled=False).ask("show me leads")
        self.assertEqual(response.mode, ChatMode.NO_DATA)
        self.assertIn("disabled", response.answer)

    def test_retrieval_summary_end_to_end(self) -> None:
        response = self.service().ask("businesses with weak seo")
        self.assertEqual(response.mode, ChatMode.RETRIEVAL_SUMMARY)
        self.assertEqual(response.retrieved_lead_ids, [self.pizzeria])
        self.assertTrue(response.grounded)
        self.assertIn("Joe's Pizzeria", response.answer)

    def test_rank_orders_by_lead_score(self) -> None:
        response = self.service().ask("show me the top leads")
        self.assertEqual(response.retrieved_lead_ids, [self.pizzeria, self.bella, self.plumber])

    def test_no_website_filter(self) -> None:
        response = self.service().ask("leads with no website")
        self.assertEqual(response.retrieved_lead_ids, [self.plumber])

    def test_detail_via_name(self) -> None:
        response = self.service().ask("Tell me about Joe's Pizzeria")
        self.assertEqual(response.mode, ChatMode.LEAD_DETAIL)
        self.assertEqual(response.retrieved_lead_ids, [self.pizzeria])

    def test_compare(self) -> None:
        response = self.service().compare([self.pizzeria, self.bella])
        self.assertEqual(response.mode, ChatMode.RETRIEVAL_SUMMARY)
        self.assertIn("|---|", response.answer)

    def test_find_similar(self) -> None:
        response = self.service().find_similar(self.pizzeria, top_k=3)
        self.assertEqual(response.retrieved_lead_ids, [self.bella, self.plumber])

    def test_explain_ranking(self) -> None:
        response = self.service().explain_ranking([self.pizzeria, self.bella])
        self.assertEqual(len(response.sources), 2)

    def test_explicit_ui_filters_apply(self) -> None:
        response = self.service().ask(
            "show me the top leads", filters={"category": ["Plumber"]}
        )
        self.assertEqual(response.retrieved_lead_ids, [self.plumber])

    def test_rag_mode_with_grounded_backend(self) -> None:
        service = self.service()
        self.set_rag(service, "Joe's Pizzeria is the strongest restaurant lead.")
        response = service.ask("businesses with weak seo")
        self.assertEqual(response.mode, ChatMode.RAG)
        self.assertEqual(response.retrieved_lead_ids, [self.pizzeria])

    def test_rag_falls_back_on_hallucination(self) -> None:
        service = self.service()
        self.set_rag(service, "Moon Cafe on Mars is the perfect target.")
        response = service.ask("businesses with weak seo")
        self.assertEqual(response.mode, ChatMode.RETRIEVAL_SUMMARY)

    def test_backend_status_defaults_to_none_backend(self) -> None:
        status = self.service().backend_status()
        self.assertIn(status["name"], {"none", "fake"})
        self.assertIn(status["mode"], {"rag", "retrieval_summary"})

    def test_session_persistence_and_restore(self) -> None:
        service = self.service(persist_sessions=True)
        session_id = service.new_session()
        first = service.ask("businesses with weak seo", session_id=session_id)
        second = service.ask("show me the top leads", session_id=session_id)
        self.assertEqual(first.retrieved_lead_ids, [self.pizzeria])
        self.assertEqual(len(second.retrieved_lead_ids), 3)

        self.assertEqual(service.last_session(), session_id)
        history = service.load_history(session_id)
        roles = [turn["role"] for turn in history]
        self.assertEqual(roles, ["user", "assistant", "user", "assistant"])
        content = [turn["content"] for turn in history]
        self.assertEqual(content[-2].lower(), "show me the top leads")

    def test_clear_session_removes_history(self) -> None:
        service = self.service(persist_sessions=True)
        session_id = service.new_session()
        service.ask("businesses with weak seo", session_id=session_id)
        service.clear_session(session_id)
        self.assertEqual(service.load_history(session_id), [])
        self.assertNotEqual(service.last_session(), session_id)

    def test_ask_never_raises_on_broken_database(self) -> None:
        broken = Path(tempfile.mkdtemp()) / "nope.sqlite"
        service = ChatService(broken, config=chat_config())
        response = service.ask("show me leads")
        self.assertEqual(response.mode, ChatMode.NO_DATA)

    def test_ask_never_raises_when_schema_missing(self) -> None:
        empty = Path(tempfile.mkdtemp()) / "empty.sqlite"
        empty.touch()
        service = ChatService(empty, config=chat_config())
        response = service.ask("show me leads")
        self.assertEqual(response.mode, ChatMode.NO_DATA)


if __name__ == "__main__":
    unittest.main()