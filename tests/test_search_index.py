"""Document builder + incremental index tests."""

from __future__ import annotations

import unittest

from src.search.cache import document_hash
from src.search.index import METADATA_KEYS, build_lead_document
from src.search.search_service import SearchService, IndexStats
from src.storage import search as search_storage

from tests.search_fixtures import SearchTestDb, test_config


class TestBuildLeadDocument(unittest.TestCase):
    def setUp(self) -> None:
        self.db = SearchTestDb()
        self.connection = self.db.connection

    def tearDown(self) -> None:
        self.db.close()

    def _intel(self, lead_id: int) -> dict:
        intel = search_storage.lead_intelligence(self.connection, lead_id)
        assert intel is not None
        return intel

    def test_returns_none_without_lead_row(self) -> None:
        self.assertIsNone(build_lead_document({"seo": {}}))

    def test_rich_document_contains_all_signals(self) -> None:
        lead_id = self.db.add_lead(
            name="Taco Stand", website="https://taco.com", category="Restaurant",
            city="Austin", state="TX", country="US", platform="WordPress",
        )
        self.db.add_detection(lead_id, "WordPress")
        self.db.add_seo(lead_id, 35, "poor", ["No meta descriptions"])
        self.db.add_visual(lead_id, 40)
        self.db.add_score(lead_id, 70, "Hot", positive=["Great reviews"], negative=["Old site"])
        self.db.add_opportunity(lead_id, "Redesign", 85, ["Outdated design"])

        doc = build_lead_document(self._intel(lead_id))
        assert doc is not None
        self.assertEqual(doc.lead_id, lead_id)
        for marker in (
            "BUSINESS:", "Taco Stand", "Restaurant", "Austin",
            "CONTACT:", "https://taco.com",
            "TECHNOLOGY:", "WordPress",
            "SEO:", "35/100", "No meta descriptions",
            "VISUAL:", "40/100",
            "OPPORTUNITIES:", "Redesign (85/100)", "Outdated design",
            "SCORING:", "70/100", "Great reviews", "Outreach angle",
        ):
            self.assertIn(marker, doc.text)
        self.assertEqual(doc.document_hash, document_hash(doc.text))
        self.assertEqual(doc.metadata["lead_id"], lead_id)
        self.assertEqual(doc.metadata["category"], "Restaurant")
        self.assertEqual(doc.metadata["seo_score"], 35)
        self.assertEqual(doc.metadata["visual_score"], 40)
        self.assertEqual(doc.metadata["opportunity_score"], 85)
        self.assertEqual(doc.metadata["lead_score"], None)
        self.assertEqual(doc.metadata["technologies"], ["wordpress"])

    def test_metadata_whitelist_only(self) -> None:
        lead_id = self.db.add_lead(name="A", website="https://a.com")
        doc = build_lead_document(self._intel(lead_id))
        assert doc is not None
        self.assertEqual(set(doc.metadata), set(METADATA_KEYS))

    def test_no_website_lead_document(self) -> None:
        lead_id = self.db.add_lead(name="No Site", website=None)
        doc = build_lead_document(self._intel(lead_id))
        assert doc is not None
        self.assertFalse(doc.metadata["website_present"])
        self.assertIn("no website detected", doc.text)

    def test_priority_falls_back_to_score_label(self) -> None:
        lead_id = self.db.add_lead(name="A", website="https://a.com", priority=None)
        self.db.add_score(lead_id, 80, "Hot")
        doc = build_lead_document(self._intel(lead_id))
        assert doc is not None
        self.assertEqual(doc.metadata["priority"], "Hot")

    def test_document_contains_contact_sections(self) -> None:
        lead_id = self.db.add_lead(
            name="Taco Stand", website="https://taco.com", category="Restaurant",
            city="Austin", state="TX", country="US",
        )
        self.db.add_contact(
            lead_id,
            owner_name="Joy",
            address="100 Main St",
            postal_code="75039",
            opening_hours="Mon-Fri 9am-5pm",
            phone="512-555-0100",
            email="joy@taco.com",
            whatsapp_url="https://wa.me/15550100",
            facebook_url="https://fb.com/taco",
            contact_page_url="https://taco.com/contact",
            contact_form_url="https://taco.com/contact-form",
            google_maps_url="https://maps.example.com/taco",
            service_areas=["Austin", "Round Rock"],
        )
        doc = build_lead_document(self._intel(lead_id))
        assert doc is not None
        for marker in (
            "LOCATION:",
            "100 Main St",
            "75039",
            "SERVICES:",
            "Austin, Round Rock",
            "CONTACT:",
            "owner: Joy",
            "phone: 512-555-0100",
            "email: joy@taco.com",
            "contact page: https://taco.com/contact",
            "contact form: https://taco.com/contact-form",
            "SOCIAL:",
            "whatsapp: https://wa.me/15550100",
            "facebook: https://fb.com/taco",
            "OPENING HOURS: Mon-Fri 9am-5pm",
        ):
            self.assertIn(marker, doc.text)

    def test_missing_contact_marked_for_searchability(self) -> None:
        lead_id = self.db.add_lead(name="Bare Co", website="https://bare.com")
        doc = build_lead_document(self._intel(lead_id))
        assert doc is not None
        self.assertIn("no phone", doc.text)
        self.assertIn("no email", doc.text)
        self.assertNotIn("LOCATION:", doc.text)
        self.assertNotIn("SOCIAL:", doc.text)


class TestSearchIndexService(unittest.TestCase):
    def setUp(self) -> None:
        self.db = SearchTestDb()
        self.service = SearchService(self.db.path, config=test_config())

    def tearDown(self) -> None:
        self.db.close()

    def test_index_run_indexes_all_run_leads(self) -> None:
        self.db.add_lead(name="Taco Stand", website="https://taco.com")
        self.db.add_lead(name="Bakery", website="https://bakery.com")
        stats = self.service.index_run(self.db.run_id)
        self.assertEqual(stats.total, 2)
        self.assertEqual(stats.indexed, 2)
        self.assertEqual(self.service.count(), 2)

    def test_index_run_is_incremental(self) -> None:
        self.db.add_lead(name="Taco Stand", website="https://taco.com")
        first = self.service.index_run(self.db.run_id)
        second = self.service.index_run(self.db.run_id)
        self.assertEqual(second.total, 1)
        self.assertEqual(second.indexed, 0)
        self.assertEqual(second.skipped, 1)
        self.assertFalse(second.changed)
        self.assertEqual(first.indexed, 1)

    def test_changed_lead_reindexes(self) -> None:
        lead_id = self.db.add_lead(name="Taco Stand", website="https://taco.com")
        self.service.index_run(self.db.run_id)
        self.db.connection.execute(
            "UPDATE leads SET business_name = 'Taco Stand II' WHERE id = ?", (lead_id,)
        )
        self.db.connection.commit()
        stats = self.service.index_run(self.db.run_id)
        self.assertEqual(stats.indexed, 1)

    def test_embedder_switch_reindexes_everything(self) -> None:
        self.db.add_lead(name="Taco Stand", website="https://taco.com")
        self.db.add_lead(name="Bakery", website="https://bakery.com")
        self.service.index_run(self.db.run_id)
        switched = SearchService(
            self.db.path,
            config=test_config(hash_dimensions=256),
        )
        stats = switched.index_run(self.db.run_id)
        self.assertEqual(stats.indexed, 2)

    def test_run_without_leads(self) -> None:
        stats = self.service.index_run(self.db.run_id + 1000)
        self.assertEqual(stats, IndexStats(total=0, indexed=0, skipped=0))

    def test_no_website_leads_are_indexed_too(self) -> None:
        self.db.add_lead(name="No Site", website=None)
        stats = self.service.index_run(self.db.run_id)
        self.assertEqual(stats.indexed, 1)

    def test_rebuild_index_clears_and_repopulates(self) -> None:
        self.db.add_lead(name="Taco Stand", website="https://taco.com")
        self.service.index_run(self.db.run_id)
        self.db.connection.execute("DELETE FROM lead_embeddings")
        self.db.connection.commit()
        stats = self.service.rebuild_index()
        self.assertEqual(stats.indexed, 1)
        self.assertEqual(self.service.count(), 1)

    def test_delete_lead_removes_embedding(self) -> None:
        lead_id = self.db.add_lead(name="Taco Stand", website="https://taco.com")
        self.service.index_run(self.db.run_id)
        self.assertTrue(self.service.delete_lead(lead_id))
        self.assertFalse(self.service.delete_lead(lead_id))
        self.assertEqual(self.service.count(), 0)

    def test_index_lead_refreshes_one(self) -> None:
        lead_id = self.db.add_lead(name="Taco Stand", website="https://taco.com")
        self.assertTrue(self.service.index_lead(lead_id))
        self.assertFalse(self.service.index_lead(lead_id))


if __name__ == "__main__":
    unittest.main()
