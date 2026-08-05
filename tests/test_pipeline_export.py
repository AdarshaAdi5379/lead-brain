"""Pipeline CSV export tests: contact columns present + NULL-safe rendering."""

from __future__ import annotations

import csv
import unittest

import main

from tests.search_fixtures import SearchTestDb

CONTACT_COLUMNS = (
    "owner_name",
    "postal_code",
    "facebook_url",
    "instagram_url",
    "linkedin_url",
    "twitter_url",
    "youtube_url",
    "whatsapp_url",
    "contact_page_url",
    "contact_form_url",
    "google_maps_url",
    "service_areas",
)


class TestPipelineExport(unittest.TestCase):
    def setUp(self) -> None:
        self.db = SearchTestDb()

    def tearDown(self) -> None:
        self.db.close()

    def _export(self) -> tuple[list[dict[str, str]], dict[str, str]]:
        out_path = main._export_csv_for_run(
            self.db.connection, run_id=self.db.run_id, min_score=0
        )
        try:
            with out_path.open(newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                headers = {str(name) for name in (reader.fieldnames or [])}
                rows = [dict(row) for row in reader]
        finally:
            out_path.unlink(missing_ok=True)
        return rows, headers

    def test_export_headers_include_all_contact_columns(self) -> None:
        self.db.add_lead(name="Taco Stand", website="https://taco.com", score=70)
        rows, headers = self._export()
        self.assertEqual(headers, set(main.EXPORT_COLUMNS))
        for column in CONTACT_COLUMNS:
            self.assertIn(column, headers)

    def test_export_round_trips_contact_values(self) -> None:
        lead_id = self.db.add_lead(
            name="Taco Stand", website="https://taco.com", category="Restaurant", score=70
        )
        self.db.add_contact(
            lead_id,
            owner_name="Joy",
            postal_code="75039",
            whatsapp_url="https://wa.me/15550100",
            contact_page_url="https://taco.com/contact",
            contact_form_url="https://taco.com/contact-form",
            google_maps_url="https://maps.example.com/taco",
            service_areas=["Austin", "Round Rock"],
        )
        rows, _ = self._export()
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["owner_name"], "Joy")
        self.assertEqual(row["postal_code"], "75039")
        self.assertEqual(row["whatsapp_url"], "https://wa.me/15550100")
        self.assertEqual(row["contact_page_url"], "https://taco.com/contact")
        self.assertEqual(row["contact_form_url"], "https://taco.com/contact-form")
        self.assertEqual(row["google_maps_url"], "https://maps.example.com/taco")
        self.assertEqual(row["service_areas"], "Austin; Round Rock")

    def test_export_null_contacts_render_empty(self) -> None:
        self.db.add_lead(name="Bare Co", website="https://bare.com", score=50)
        rows, _ = self._export()
        self.assertEqual(len(rows), 1)
        row = rows[0]
        for column in CONTACT_COLUMNS:
            self.assertEqual(row[column], "", f"{column} should render empty")


if __name__ == "__main__":
    unittest.main()