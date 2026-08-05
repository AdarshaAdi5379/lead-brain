import sqlite3
import unittest

from tests.contact_fixtures import GRAPH_PAGE, JSONLD_HOMEPAGE
from src.contact.recovery import extract_email_candidates, extract_phone_candidates
from src.contact.schema import merge_contact_signals
from src.contact.sources import (
    JSON_LD,
    CSV,
    LLM,
    MAILTO,
    SCHEMA,
    TEL,
    VISIBLE_TEXT,
    ContactCandidate,
    better_contact,
    pick_across_sources,
    pick_best_email,
    pick_best_phone,
)
from src.contact.extractor import (
    extract_contact_signals,
    extract_contact_signals_from_crawl,
)
from src.storage.db import init_db
from src.storage.leads import LeadUpsert, upsert_lead

HOME = "https://acme.example.com/"


def _sources(candidates) -> set[str]:
    return {candidate.source for candidate in candidates}


class TestEmailCandidates(unittest.TestCase):
    def test_visible_text_emails(self) -> None:
        html = '<html><body><p>Email sales@acme.example.com or support@acme.example.com.</p></body></html>'
        candidates = extract_email_candidates(html)
        values = sorted(c.value for c in candidates)
        self.assertEqual(values, ["sales@acme.example.com", "support@acme.example.com"])
        self.assertEqual(_sources(candidates), {VISIBLE_TEXT})

    def test_mailto_links(self) -> None:
        html = '<html><body><a href="mailto:hello@acme.example.com">Email us</a></body></html>'
        candidates = extract_email_candidates(html)
        self.assertEqual([c.value for c in candidates], ["hello@acme.example.com"])
        self.assertEqual(_sources(candidates), {MAILTO})

    def test_mailto_list_and_query_stripped(self) -> None:
        html = (
            '<a href="mailto:a@acme.example.com,b@acme.example.com?subject=Hi">list</a>'
        )
        candidates = extract_email_candidates(html)
        values = sorted(c.value for c in candidates)
        self.assertEqual(values, ["a@acme.example.com", "b@acme.example.com"])

    def test_json_ld_email_source(self) -> None:
        candidates = extract_email_candidates(JSONLD_HOMEPAGE)
        self.assertEqual([c.value for c in candidates], ["office@acme.example.com"])
        self.assertEqual(_sources(candidates), {JSON_LD})

    def test_microdata_email_source(self) -> None:
        html = (
            '<html><body><span itemprop="email">michelle@acme.example.com</span>'
            '<meta itemprop="email" content="meta@acme.example.com"></body></html>'
        )
        candidates = extract_email_candidates(html)
        values = sorted(c.value for c in candidates)
        self.assertEqual(values, ["meta@acme.example.com", "michelle@acme.example.com"])
        self.assertEqual(_sources(candidates), {SCHEMA})

    def test_junk_emails_dropped(self) -> None:
        html = '<html><body><p>not.an.email and a@b and x@example.</p></body></html>'
        self.assertEqual(extract_email_candidates(html), [])


class TestPhoneCandidates(unittest.TestCase):
    def test_tel_links(self) -> None:
        html = '<html><body><a href="tel:+1-512-555-0100">Call</a></body></html>'
        candidates = extract_phone_candidates(html)
        self.assertEqual([c.value for c in candidates], ["+1-512-555-0100"])
        self.assertEqual(_sources(candidates), {TEL})

    def test_visible_text_international_phone(self) -> None:
        html = '<html><body><p>Call us today at +1-512-555-0100, Mon-Fri.</p></body></html>'
        candidates = extract_phone_candidates(html)
        self.assertIn("+1-512-555-0100", [c.value for c in candidates])
        self.assertEqual(_sources(candidates), {VISIBLE_TEXT})

    def test_visible_text_plain_phone(self) -> None:
        html = '<html><body><p>Text 512 555 0100 for an appointment.</p></body></html>'
        candidates = extract_phone_candidates(html)
        self.assertEqual([c.value for c in candidates], ["512 555 0100"])

    def test_years_dates_and_ranges_rejected(self) -> None:
        html = (
            "<html><body><p>Serving you since 2004. "
            "Hours: 05-10-2024 nothing. School years 2018-2024 ended. "
            "Short 1234 is not a phone.</p></body></html>"
        )
        candidates = extract_phone_candidates(html)
        values = {c.value for c in candidates}
        self.assertNotIn("2004", values)
        self.assertNotIn("05-10-2024", values)
        self.assertNotIn("2018-2024", values)
        self.assertNotIn("1234", values)

    def test_json_ld_phone_source(self) -> None:
        candidates = extract_phone_candidates(JSONLD_HOMEPAGE)
        self.assertEqual([c.value for c in candidates], ["+1-512-555-0100"])

    def test_empty_html_yields_nothing(self) -> None:
        self.assertEqual(extract_email_candidates(""), [])
        self.assertEqual(extract_phone_candidates(""), [])


class TestBestPick(unittest.TestCase):
    def test_business_domain_email_preferred(self) -> None:
        candidates = [
            ContactCandidate("info@acme.example.com", VISIBLE_TEXT, order=0),
            ContactCandidate("office@other-domain.example", VISIBLE_TEXT, order=1),
        ]
        best = pick_best_email(candidates, "https://www.acme.example.com/")
        self.assertEqual(best.value, "info@acme.example.com")

    def test_prefix_ranking_breaks_company_domain_ties(self) -> None:
        candidates = [
            ContactCandidate("info@acme.example.com", VISIBLE_TEXT, order=0),
            ContactCandidate("sales@acme.example.com", VISIBLE_TEXT, order=1),
        ]
        best = pick_best_email(candidates, "https://acme.example.com/")
        self.assertEqual(best.value, "sales@acme.example.com")

    def test_source_rank_beats_prefix_for_same_value(self) -> None:
        candidates = [
            ContactCandidate("office@acme.example.com", VISIBLE_TEXT, order=0),
            ContactCandidate("office@acme.example.com", JSON_LD, order=1),
        ]
        best = pick_best_email(candidates, "https://acme.example.com/")
        self.assertEqual(best.source, JSON_LD)

    def test_leading_plus_phone_preferred(self) -> None:
        candidates = [
            ContactCandidate("5125550100", VISIBLE_TEXT, order=0),
            ContactCandidate("+1-512-555-0100", TEL, order=1),
        ]
        best = pick_best_phone(candidates)
        self.assertEqual(best.value, "+1-512-555-0100")


class TestBetterContact(unittest.TestCase):
    def test_missing_incoming_keeps_existing(self) -> None:
        self.assertEqual(
            better_contact("+1-512-555-0100", JSON_LD, 1.0, None, CSV, None),
            ("+1-512-555-0100", JSON_LD, 1.0),
        )

    def test_missing_existing_takes_incoming(self) -> None:
        self.assertEqual(
            better_contact(None, None, None, "a@acme.example.com", CSV, None),
            ("a@acme.example.com", CSV, None),
        )

    def test_same_value_upgrades_source_only(self) -> None:
        self.assertEqual(
            better_contact("info@acme.example.com", None, None, "info@acme.example.com", CSV, None),
            ("info@acme.example.com", CSV, None),
        )

    def test_higher_rank_incoming_replaces(self) -> None:
        self.assertEqual(
            better_contact("a@acme.example.com", CSV, None, "b@acme.example.com", JSON_LD, None),
            ("b@acme.example.com", JSON_LD, None),
        )

    def test_lower_rank_incoming_keeps_existing(self) -> None:
        self.assertEqual(
            better_contact("+1-512-555-0100", VISIBLE_TEXT, None, "+91-80-4493-2200", CSV, None),
            ("+1-512-555-0100", VISIBLE_TEXT, None),
        )

    def test_same_rank_tie_keeps_existing(self) -> None:
        self.assertEqual(
            better_contact("a@acme.example.com", VISIBLE_TEXT, 0.9, "b@acme.example.com", VISIBLE_TEXT, 0.8),
            ("a@acme.example.com", VISIBLE_TEXT, 0.9),
        )

    def test_same_rank_higher_confidence_wins(self) -> None:
        self.assertEqual(
            better_contact("a@acme.example.com", VISIBLE_TEXT, 0.8, "b@acme.example.com", VISIBLE_TEXT, 0.9),
            ("b@acme.example.com", VISIBLE_TEXT, 0.9),
        )

    def test_pick_across_sources_order(self) -> None:
        value, source, _ = pick_across_sources(
            ("+1-512-555-0100", JSON_LD, None),
            ("+91-80-4493-2200", LLM, None),
            ("5125550100", CSV, None),
        )
        self.assertEqual(value, "+1-512-555-0100")
        self.assertEqual(source, JSON_LD)


class TestPageResolution(unittest.TestCase):
    def test_mailto_and_tel_win_on_their_page(self) -> None:
        html = (
            '<html><body><p>Call 512.555.0100 or mail office@acme.example.com.</p>'
            '<a href="tel:+1-512-555-0100">tel</a>'
            '<a href="mailto:office@acme.example.com">mail</a></body></html>'
        )
        signals = extract_contact_signals(html, HOME, page_label="HOME")
        self.assertEqual(signals.phone, "+1-512-555-0100")
        self.assertEqual(signals.phone_source, TEL)
        self.assertEqual(signals.email, "office@acme.example.com")
        self.assertEqual(signals.email_source, MAILTO)

    def test_json_ld_beats_visible_text(self) -> None:
        html = JSONLD_HOMEPAGE + "<p>Call 512-555-9999 or email office@acme.example.com</p>"
        signals = extract_contact_signals(html, HOME, page_label="HOME")
        self.assertEqual(signals.phone, "+1-512-555-0100")
        self.assertEqual(signals.phone_source, JSON_LD)
        self.assertEqual(signals.email, "office@acme.example.com")
        self.assertEqual(signals.email_source, JSON_LD)

    def test_prefix_preference_beats_source_for_distinct_values(self) -> None:
        html = (
            '<html><body><p>mail sales@acme.example.com</p>'
            '<a href="mailto:office@acme.example.com">office</a></body></html>'
        )
        signals = extract_contact_signals(html, HOME, page_label="HOME")
        self.assertEqual(signals.email, "sales@acme.example.com")

    def test_email_and_phone_candidates_populated(self) -> None:
        signals = extract_contact_signals(JSONLD_HOMEPAGE, HOME, page_label="HOME")
        self.assertTrue(signals.email_candidates)
        self.assertTrue(signals.phone_candidates)


class TestMergeAndCrawlResolution(unittest.TestCase):
    def test_merge_unions_candidates(self) -> None:
        first = extract_contact_signals(JSONLD_HOMEPAGE, HOME, page_label="HOME")
        second_page = "<html><body><p>mail info@acme.example.com</p></body></html>"
        second = extract_contact_signals(second_page, HOME + "contact", page_label="Contact")
        merged = merge_contact_signals([first, second])
        email_values = [c.value for c in merged.email_candidates]
        self.assertIn("office@acme.example.com", email_values)
        self.assertIn("info@acme.example.com", email_values)

    def test_crawl_resolution_picks_stronger_page_source(self) -> None:
        class Page:
            def __init__(self, label: str, html: str, url: str) -> None:
                self.label = label
                self.url = url
                self.contact = extract_contact_signals(html, url, page_label=label)

        class Crawl:
            pages = [
                Page("HOME", "<html><body><p>Call 512-555-9999</p></body></html>", HOME),
                Page("Contact", GRAPH_PAGE, HOME + "contact"),
            ]

        signals = extract_contact_signals_from_crawl(Crawl())
        self.assertEqual(signals.phone, "+1-512-555-0199")
        self.assertEqual(signals.phone_source, JSON_LD)


class TestUpsertPreservation(unittest.TestCase):
    def setUp(self) -> None:
        self.connection = sqlite3.connect(":memory:")
        self.connection.row_factory = sqlite3.Row
        init_db(self.connection)
        self.connection.execute("INSERT INTO scraping_runs (started_at) VALUES (datetime('now'))")
        self.run_id = int(
            self.connection.execute("SELECT run_id FROM scraping_runs").fetchone()["run_id"]
        )

    def tearDown(self) -> None:
        self.connection.close()

    def _row(self, key: str) -> sqlite3.Row:
        return self.connection.execute(
            "SELECT phone, email, phone_source, email_source FROM leads"
            " WHERE website_url_normalized = ?",
            (key,),
        ).fetchone()

    def test_weaker_rerun_never_overwrites(self) -> None:
        key = upsert_lead(
            self.connection,
            LeadUpsert(
                website_url="https://acme.example.com/",
                phone="+1-512-555-0100",
                phone_source=JSON_LD,
                email="office@acme.example.com",
                email_source=JSON_LD,
                run_id=self.run_id,
            ),
        )
        upsert_lead(
            self.connection,
            LeadUpsert(
                website_url="https://acme.example.com/",
                phone="512-555-9999",
                phone_source=CSV,
                email="sales@acme.example.com",
                email_source=CSV,
                run_id=self.run_id,
            ),
        )
        row = self._row(key)
        self.assertEqual(row["phone"], "+1-512-555-0100")
        self.assertEqual(row["email"], "office@acme.example.com")

    def test_stronger_rerun_replaces(self) -> None:
        key = upsert_lead(
            self.connection,
            LeadUpsert(
                website_url="https://acme.example.com/",
                phone="512-555-9999",
                phone_source=CSV,
                run_id=self.run_id,
            ),
        )
        upsert_lead(
            self.connection,
            LeadUpsert(
                website_url="https://acme.example.com/",
                phone="+1-512-555-0100",
                phone_source=JSON_LD,
                run_id=self.run_id,
            ),
        )
        row = self._row(key)
        self.assertEqual(row["phone"], "+1-512-555-0100")
        self.assertEqual(row["phone_source"], JSON_LD)

    def test_same_value_rerun_records_source(self) -> None:
        key = upsert_lead(
            self.connection,
            LeadUpsert(
                website_url="https://acme.example.com/",
                phone="+1-512-555-0100",
                run_id=self.run_id,
            ),
        )
        upsert_lead(
            self.connection,
            LeadUpsert(
                website_url="https://acme.example.com/",
                phone="+1-512-555-0100",
                phone_source=JSON_LD,
                run_id=self.run_id,
            ),
        )
        row = self._row(key)
        self.assertEqual(row["phone"], "+1-512-555-0100")
        self.assertEqual(row["phone_source"], JSON_LD)

    def test_null_rerun_keeps_existing(self) -> None:
        key = upsert_lead(
            self.connection,
            LeadUpsert(
                website_url="https://acme.example.com/",
                email="office@acme.example.com",
                email_source=JSON_LD,
                run_id=self.run_id,
            ),
        )
        upsert_lead(
            self.connection,
            LeadUpsert(website_url="https://acme.example.com/", run_id=self.run_id),
        )
        row = self._row(key)
        self.assertEqual(row["email"], "office@acme.example.com")
        self.assertEqual(row["email_source"], JSON_LD)


if __name__ == "__main__":
    unittest.main()