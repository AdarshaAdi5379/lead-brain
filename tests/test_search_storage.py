"""Search storage tests: lead_embeddings persistence + intelligence join."""

from __future__ import annotations

import unittest

from src.storage import search as search_storage
from src.storage.db import connect, init_db
from src.storage.leads import LeadUpsert, upsert_lead
from src.storage.normalization import normalize_url_for_dedupe
from src.storage.runs import start_run
from src.storage.technologies import get_lead_id_by_url

from tests.search_fixtures import SearchTestDb


class TestEmbeddingPersistence(unittest.TestCase):
    def setUp(self) -> None:
        self.db = SearchTestDb()
        self.connection = self.db.connection

    def tearDown(self) -> None:
        self.db.close()

    def test_upsert_then_get(self) -> None:
        lead_id = self.db.add_lead(name="Taco Stand", website="https://taco.com")
        search_storage.upsert_embedding(
            self.connection,
            lead_id=lead_id,
            document_hash="abc",
            embedding_hash="def",
            embedder_id="hash-ngram-128",
            document_text="BUSINESS: Taco Stand",
            metadata={"lead_id": lead_id, "category": "Restaurant"},
            embedding=[0.5, 0.5],
        )
        row = search_storage.get_embedding_row(self.connection, lead_id)
        assert row is not None
        self.assertEqual(row["document_hash"], "abc")
        self.assertEqual(row["embedding_hash"], "def")
        self.assertEqual(row["embedder_id"], "hash-ngram-128")
        self.assertEqual(row["metadata"], {"lead_id": lead_id, "category": "Restaurant"})
        self.assertEqual(row["embedding"], [0.5, 0.5])
        self.assertEqual(row["embedding_dim"], 2)

    def test_upsert_replaces_same_lead(self) -> None:
        lead_id = self.db.add_lead(name="Taco Stand", website="https://taco.com")
        for text in ("v1", "v2"):
            search_storage.upsert_embedding(
                self.connection,
                lead_id=lead_id, document_hash=text, embedding_hash=text,
                embedder_id="e", document_text=text, metadata={}, embedding=[1.0],
            )
        rows = search_storage.all_embedding_rows(self.connection)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["document_text"], "v2")

    def test_delete_and_count(self) -> None:
        lead_id = self.db.add_lead(name="Taco Stand", website="https://taco.com")
        search_storage.upsert_embedding(
            self.connection, lead_id=lead_id, document_hash="h", embedding_hash="h",
            embedder_id="e", document_text="t", metadata={}, embedding=[1.0],
        )
        self.assertEqual(search_storage.count_embeddings(self.connection), 1)
        self.assertFalse(search_storage.delete_embedding(self.connection, 999))
        self.assertTrue(search_storage.delete_embedding(self.connection, lead_id))
        self.assertEqual(search_storage.count_embeddings(self.connection), 0)

    def test_clear(self) -> None:
        for name in ("A", "B"):
            lead_id = self.db.add_lead(name=name, website=f"https://{name.lower()}.com")
            search_storage.upsert_embedding(
                self.connection, lead_id=lead_id, document_hash="h", embedding_hash="h",
                embedder_id="e", document_text="t", metadata={}, embedding=[1.0],
            )
        self.assertEqual(search_storage.clear_embeddings(self.connection), 2)
        self.assertEqual(search_storage.count_embeddings(self.connection), 0)

    def test_embeddings_for_run(self) -> None:
        lead_id = self.db.add_lead(name="A", website="https://a.com")
        search_storage.upsert_embedding(
            self.connection, lead_id=lead_id, document_hash="h", embedding_hash="h",
            embedder_id="e", document_text="t", metadata={}, embedding=[1.0],
        )
        rows = search_storage.embeddings_for_run(self.connection, self.db.run_id)
        self.assertEqual([row["lead_id"] for row in rows], [lead_id])

    def test_missing_row_returns_none(self) -> None:
        self.assertIsNone(search_storage.get_embedding_row(self.connection, 42))


class TestLeadIntelligence(unittest.TestCase):
    def setUp(self) -> None:
        self.db = SearchTestDb()
        self.connection = self.db.connection

    def tearDown(self) -> None:
        self.db.close()

    def test_lead_intelligence_joins_everything(self) -> None:
        lead_id = self.db.add_lead(
            name="Taco Stand", website="https://taco.com", category="Restaurant",
            city="Austin", state="TX", country="US", platform="WordPress",
            priority="Hot", score=75, extracted_at="2026-07-01T12:00:00+00:00",
        )
        self.db.add_detection(lead_id, "WordPress")
        self.db.add_seo(lead_id, 35, "poor", ["No meta descriptions"])
        self.db.add_visual(lead_id, 40)
        self.db.add_score(lead_id, 70, "Hot", positive=["Good", "Nice"], negative=["Old"])
        self.db.add_opportunity(lead_id, "Redesign", 85)

        intel = search_storage.lead_intelligence(self.connection, lead_id)
        assert intel is not None
        self.assertEqual(intel["lead"]["business_name"], "Taco Stand")
        self.assertEqual(intel["lead"]["priority"], "Hot")
        self.assertEqual([d["technology_name"] for d in intel["detections"]], ["WordPress"])
        self.assertEqual(intel["seo"]["site_score"], 35)
        self.assertEqual(intel["seo"]["severity_summary"][0]["code"], "thin_content")
        self.assertEqual(intel["visual"]["visual_score"], 40)
        self.assertEqual(intel["score"]["final_score"], 70)
        self.assertEqual(intel["score"]["top_positive_reasons"], ["Good", "Nice"])
        self.assertEqual(intel["opportunities"][0]["label"], "Redesign")
        self.assertEqual(intel["opportunities"][0]["evidence"], ["Outdated design"])

    def test_lead_intelligence_missing_lead(self) -> None:
        self.assertIsNone(search_storage.lead_intelligence(self.connection, 999))

    def test_leads_intelligence_filters_by_run(self) -> None:
        first = self.db.add_lead(name="A", website="https://a.com")
        other_run = start_run(self.connection)
        upsert_lead(
            self.connection,
            LeadUpsert(
                website_url="https://b.com", business_name="B",
                run_id=other_run, extraction_success=True,
            ),
        )
        other = get_lead_id_by_url(self.connection, normalize_url_for_dedupe("https://b.com"))
        assert other is not None
        by_run = search_storage.leads_intelligence(self.connection, run_id=self.db.run_id)
        self.assertEqual(list(by_run), [first])
        all_leads = search_storage.leads_intelligence(self.connection)
        self.assertEqual(set(all_leads), {first, other})

    def test_leads_intelligence_by_ids(self) -> None:
        first = self.db.add_lead(name="A", website="https://a.com")
        second = self.db.add_lead(name="B", website="https://b.com")
        subset = search_storage.leads_intelligence(self.connection, lead_ids=[second])
        self.assertEqual(list(subset), [second])
        self.assertIn(first, search_storage.leads_intelligence(self.connection))

    def test_leads_intelligence_empty(self) -> None:
        self.assertEqual(search_storage.leads_intelligence(self.connection), {})

    def test_minimal_lead_has_none_sections(self) -> None:
        lead_id = self.db.add_lead(name="No Website Co", website=None)
        intel = search_storage.lead_intelligence(self.connection, lead_id)
        assert intel is not None
        self.assertIsNone(intel["seo"])
        self.assertIsNone(intel["visual"])
        self.assertIsNone(intel["score"])
        self.assertEqual(intel["opportunities"], [])
        self.assertEqual(intel["lead"]["service_areas"], [])

    def test_service_areas_decoded_on_lead(self) -> None:
        lead_id = self.db.add_lead(name="Taco Stand", website="https://taco.com")
        self.db.add_contact(lead_id, service_areas=["Austin", "Round Rock"])
        intel = search_storage.lead_intelligence(self.connection, lead_id)
        assert intel is not None
        self.assertEqual(intel["lead"]["service_areas"], ["Austin", "Round Rock"])
        self.assertIn("service_areas_json", intel["lead"])

    def test_bad_service_areas_json_decodes_empty(self) -> None:
        lead_id = self.db.add_lead(name="Taco Stand", website="https://taco.com")
        self.connection.execute(
            "UPDATE leads SET service_areas_json = 'not json' WHERE id = ?", (lead_id,)
        )
        self.connection.commit()
        intel = search_storage.lead_intelligence(self.connection, lead_id)
        assert intel is not None
        self.assertEqual(intel["lead"]["service_areas"], [])


class TestDecodeRobustness(unittest.TestCase):
    def setUp(self) -> None:
        self.db = SearchTestDb()
        self.connection = self.db.connection
        self.path = self.db.path

    def tearDown(self) -> None:
        self.db.close()

    def test_bad_json_decodes_to_fallback(self) -> None:
        lead_id = self.db.add_lead(name="A", website="https://a.com")
        search_storage.upsert_embedding(
            self.connection, lead_id=lead_id, document_hash="h", embedding_hash="h",
            embedder_id="e", document_text="t", metadata={}, embedding=[1.0],
        )
        self.connection.execute(
            "UPDATE lead_embeddings SET metadata_json = 'not json', embedding_json = 'also not json'"
            " WHERE lead_id = ?",
            (lead_id,),
        )
        self.connection.commit()
        row = search_storage.get_embedding_row(self.connection, lead_id)
        assert row is not None
        self.assertEqual(row["metadata"], {})
        self.assertEqual(row["embedding"], [])


if __name__ == "__main__":
    unittest.main()
