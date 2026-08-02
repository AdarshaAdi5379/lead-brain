import sqlite3
import unittest

from src.seo.site_audit import audit_site
from src.storage.db import init_db
from src.storage.leads import LeadUpsert, upsert_lead
from src.storage.seo import audits_by_lead, audits_for_run, page_audits_for_audit, replace_audit
from src.storage.technologies import get_lead_id_by_url


def _make_db() -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    init_db(connection)
    return connection


def _fake_audit_dicts():
    from types import SimpleNamespace

    html = (
        "<html><head><title>Acme</title>"
        '<meta name="description" content="' + "d" * 130 + '">'
        "</head><body><h1>H</h1><h2>H2</h2><p>" + "word " * 400 + "</p>"
        '<a href="/a">A</a><a href="/b">B</a><a href="/c">C</a>'
        "</body></html>"
    )
    pages = [
        SimpleNamespace(url="https://example.com/", label="HOME", title="Acme", text="x", html=html),
        SimpleNamespace(url="https://example.com/contact", label="CONTACT", title="Contact", text="y", html=html),
    ]
    audit = audit_site(pages, "https://example.com/")
    data = audit.to_dict()
    return data, data.pop("pages"), audit


class TestSeoStorage(unittest.TestCase):
    def test_replace_and_read_back(self) -> None:
        connection = _make_db()
        try:
            normalized = upsert_lead(
                connection, LeadUpsert(website_url="https://example.com/", business_name="Acme")
            )
            lead_id = get_lead_id_by_url(connection, normalized)
            site, pages, audit = _fake_audit_dicts()

            audit_id = replace_audit(connection, lead_id, site, pages)

            stored = audits_by_lead(connection)
            self.assertIn(lead_id, stored)
            self.assertEqual(stored[lead_id]["site_score"], site["site_score"])
            self.assertEqual(stored[lead_id]["overall_health"], site["overall_health"])
            self.assertEqual(len(stored[lead_id]["severity_summary"]), len(site["severity_summary"]))

            page_rows = page_audits_for_audit(connection, audit_id)
            self.assertEqual(len(page_rows), 2)
            by_url = {row["url"]: row for row in page_rows}
            self.assertIn("https://example.com/contact", by_url)
            contact = by_url["https://example.com/contact"]
            self.assertEqual(contact["title_present"], 1)
            expected = next(p for p in audit.pages if p.url == "https://example.com/contact")
            self.assertEqual(contact["score"], expected.score)
            self.assertIsInstance(contact["issues"], list)
        finally:
            connection.close()
    def test_replace_is_deterministic_on_rerun(self) -> None:
        connection = _make_db()
        try:
            normalized = upsert_lead(
                connection, LeadUpsert(website_url="https://example.com/")
            )
            lead_id = get_lead_id_by_url(connection, normalized)
            site, pages, audit = _fake_audit_dicts()

            replace_audit(connection, lead_id, site, pages)
            first_id = connection.execute(
                "SELECT id FROM seo_audits WHERE lead_id = ?", (lead_id,)
            ).fetchone()["id"]

            site["site_score"] = 55
            replace_audit(connection, lead_id, site, pages)
            second_id = connection.execute(
                "SELECT id FROM seo_audits WHERE lead_id = ?", (lead_id,)
            ).fetchone()["id"]

            self.assertNotEqual(first_id, second_id)
            rows = connection.execute("SELECT COUNT(*) AS n FROM seo_audits WHERE lead_id = ?", (lead_id,))
            self.assertEqual(rows.fetchone()["n"], 1)
            page_rows = connection.execute("SELECT COUNT(*) AS n FROM seo_page_audits").fetchone()
            self.assertEqual(page_rows["n"], 2)
            stored = audits_by_lead(connection)[lead_id]
            self.assertEqual(stored["site_score"], 55)
        finally:
            connection.close()

    def test_audits_for_run(self) -> None:
        connection = _make_db()
        try:
            connection.execute("INSERT INTO scraping_runs (started_at) VALUES (datetime('now'))")
            run_id = connection.execute("SELECT last_insert_rowid() AS rid").fetchone()["rid"]

            normalized = upsert_lead(
                connection,
                LeadUpsert(
                    website_url="https://example.com/", business_name="Acme", run_id=run_id
                ),
            )
            lead_id = get_lead_id_by_url(connection, normalized)
            site, pages, _ = _fake_audit_dicts()
            replace_audit(connection, lead_id, site, pages)

            rows = audits_for_run(connection, run_id)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["lead_id"], lead_id)
            self.assertIn("raw_summary_json", rows[0])
            self.assertIsInstance(rows[0]["raw_summary_json"], dict)
        finally:
            connection.close()


if __name__ == "__main__":
    unittest.main()
