"""Unit tests for the CRM sync/merge layer (src/crm/sync.py).

Covers auto-fill from SQLite, manual-wins merge, and manual field write-back.
"""

from __future__ import annotations

import unittest

from tests.search_fixtures import SearchTestDb

from src.crm.columns import DEFAULT_STATUS, MANUAL_COLUMNS
from src.crm.sync import (
    build_sqlite_rows,
    has_manual_edits,
    merge_rows,
    sync_manual_to_sqlite,
)
from src.crm.workbook import normalise_row
from src.storage.search import lead_intelligence


class SyncAutoFillTest(unittest.TestCase):
    def setUp(self) -> None:
        self.db = SearchTestDb()

    def tearDown(self) -> None:
        self.db.close()

    def test_auto_rows_cover_all_columns(self) -> None:
        db = self.db
        lid = db.add_lead(
            name="Taco Stand", website="https://taco.com", category="Restaurant",
            city="Austin", state="TX", country="US", platform="WordPress",
            priority="Hot", score=70,
        )
        db.add_contact(
            lid, country="US", owner_name="Joy", address="100 Main St",
            opening_hours="Mon-Fri 9-5", phone="512-555-0100",
            email="joy@taco.com", facebook_url="https://fb.com/taco",
        )
        db.add_score(lid, final_score=82, priority_label="Hot",
                     angle="Offer a modern website redesign.")
        db.add_seo(lid, 55, "good")
        db.add_visual(lid, 40)
        db.add_opportunity(lid, "Redesign", 85)

        rows = build_sqlite_rows(db.connection)
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["lead_id"], lid)
        self.assertEqual(row["business_name"], "Taco Stand")
        self.assertEqual(row["category"], "Restaurant")
        self.assertEqual(row["city"], "Austin")
        self.assertEqual(row["state"], "TX")
        self.assertEqual(row["country"], "US")
        self.assertEqual(row["platform"], "WordPress")
        self.assertEqual(row["website_url"], "https://taco.com")
        self.assertEqual(row["phone"], "512-555-0100")
        self.assertEqual(row["email"], "joy@taco.com")
        self.assertEqual(row["opening_hours"], "Mon-Fri 9-5")
        self.assertEqual(row["facebook_url"], "https://fb.com/taco")
        self.assertEqual(row["lead_score"], 82)
        self.assertEqual(row["seo_score"], 55)
        self.assertEqual(row["visual_score"], 40)
        self.assertEqual(row["opportunity_score"], 85)
        self.assertEqual(row["priority_label"], "Hot")
        self.assertEqual(row["recommended_outreach_angle"], "Offer a modern website redesign.")
        self.assertEqual(row["best_contact_method"], "email")
        self.assertEqual(row["status"], DEFAULT_STATUS)
        # All 34 columns present.
        from src.crm.columns import COLUMNS
        self.assertEqual(set(COLUMNS), set(row.keys()))

    def test_no_opportunities_leaves_blank_score(self) -> None:
        db = self.db
        lid = db.add_lead(name="Bakery", website="https://bakery.com")
        db.add_score(lid, final_score=60, priority_label="Warm")
        rows = build_sqlite_rows(db.connection)
        self.assertIsNone(rows[0]["opportunity_score"])
        self.assertEqual(rows[0]["priority_label"], "Warm")
        self.assertEqual(rows[0]["lead_score"], 60)

    def test_blank_lead_stays_blank(self) -> None:
        db = self.db
        db.add_lead(name="No Website Yet", website=None, category="Cafe")
        rows = build_sqlite_rows(db.connection)
        self.assertEqual(len(rows), 1)
        self.assertIsNone(rows[0]["website_url"])
        for column in ("address", "phone", "email"):
            self.assertIsNone(rows[0][column])

    def test_orders_by_lead_id(self) -> None:
        db = self.db
        first = db.add_lead(name="A", website="https://a.com")
        second = db.add_lead(name="B", website="https://b.com")
        rows = build_sqlite_rows(db.connection)
        self.assertEqual([r["lead_id"] for r in rows], sorted([first, second]))


class SyncMergeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.db = SearchTestDb()
        self.lid = self.db.add_lead(name="Taco Stand", website="https://taco.com")
        self.db.add_score(self.lid, final_score=70, priority_label="Warm")

    def tearDown(self) -> None:
        self.db.close()

    def test_manual_wins_on_merge(self) -> None:
        auto = build_sqlite_rows(self.db.connection)
        auto[0]["status"] = DEFAULT_STATUS
        manual = [
            {
                "lead_id": self.lid,
                "status": "Contacted",
                "notes": "Left a voicemail",
                "assigned_to": "Me",
                "last_contacted": "2026-08-01",
                "next_follow_up": "2026-08-10",
                "best_contact_method": "phone",
            }
        ]
        merged = merge_rows(auto, manual)
        self.assertEqual(merged[0]["status"], "Contacted")
        self.assertEqual(merged[0]["notes"], "Left a voicemail")
        self.assertEqual(merged[0]["next_follow_up"], "2026-08-10")
        # Auto values (scores, name) are preserved.
        self.assertEqual(merged[0]["lead_score"], 70)
        self.assertEqual(merged[0]["business_name"], "Taco Stand")

    def test_empty_manual_status_falls_back_to_default(self) -> None:
        auto = build_sqlite_rows(self.db.connection)
        manual = [{"lead_id": self.lid, "status": "", "notes": "hi"}]
        merged = merge_rows(auto, manual)
        self.assertEqual(merged[0]["status"], DEFAULT_STATUS)
        self.assertEqual(merged[0]["notes"], "hi")

    def test_invalid_manual_date_dropped(self) -> None:
        auto = build_sqlite_rows(self.db.connection)
        manual = [{"lead_id": self.lid, "status": "Contacted", "next_follow_up": "soon"}]
        merged = merge_rows(auto, manual)
        self.assertEqual(merged[0]["status"], "Contacted")
        self.assertIsNone(merged[0]["next_follow_up"])

    def test_orphan_manual_rows_are_dropped(self) -> None:
        auto = build_sqlite_rows(self.db.connection)
        manual = [{"lead_id": 999, "status": "Contacted"}]
        merged = merge_rows(auto, manual)
        self.assertEqual([r["lead_id"] for r in merged], [self.lid])
        self.assertEqual(merged[0]["status"], DEFAULT_STATUS)


class SyncWriteBackTest(unittest.TestCase):
    def setUp(self) -> None:
        self.db = SearchTestDb()
        self.lid = self.db.add_lead(name="Taco Stand", website="https://taco.com")

    def tearDown(self) -> None:
        self.db.close()

    def test_writes_manual_fields_to_sqlite(self) -> None:
        rows = [
            {
                "lead_id": self.lid,
                "status": "Called",
                "notes": "Interested",
                "assigned_to": "Ada",
                "last_contacted": "2026-07-30",
                "next_follow_up": "2026-08-12",
                "best_contact_method": "phone",
            }
        ]
        written = sync_manual_to_sqlite(self.db.connection, rows)
        self.assertEqual(written, 1)
        lead = dict(
            self.db.connection.execute(
                "SELECT status, notes, assigned_to, last_contacted, next_follow_up,"
                " best_contact_method FROM leads WHERE id = ?", (self.lid,)
            ).fetchone()
        )
        self.assertEqual(lead["status"], "Called")
        self.assertEqual(lead["notes"], "Interested")
        self.assertEqual(lead["assigned_to"], "Ada")
        self.assertEqual(lead["last_contacted"], "2026-07-30")
        self.assertEqual(lead["next_follow_up"], "2026-08-12")
        self.assertEqual(lead["best_contact_method"], "phone")

    def test_missing_lead_does_not_crash(self) -> None:
        rows = [{"lead_id": 9999, "status": "X"}]
        written = sync_manual_to_sqlite(self.db.connection, rows)
        self.assertEqual(written, 0)

    def test_empty_values_do_not_wipe_existing(self) -> None:
        sync_manual_to_sqlite(self.db.connection, [{"lead_id": self.lid, "status": "Called"}])
        written = sync_manual_to_sqlite(
            self.db.connection, [{"lead_id": self.lid, "status": None}]
        )
        self.assertEqual(written, 0)
        status = self.db.connection.execute(
            "SELECT status FROM leads WHERE id = ?", (self.lid,)
        ).fetchone()["status"]
        self.assertEqual(status, "Called")

    def test_has_manual_edits(self) -> None:
        self.assertFalse(has_manual_edits([{"lead_id": self.lid, "status": None}]))
        self.assertTrue(has_manual_edits([{"lead_id": self.lid, "status": "Called"}]))


if __name__ == "__main__":
    unittest.main()