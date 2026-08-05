from __future__ import annotations

import unittest

from tests.contact_fixtures import (
    CONTACT_FORM_PAGE,
    GRAPH_PAGE,
    JSONLD_HOMEPAGE,
    LOGIN_ONLY_PAGE,
    NO_FORM_PAGE,
    SOCIALS_PAGE,
)
from src.contact.extractor import (
    extract_contact_signals,
    extract_contact_signals_from_crawl,
    extract_contact_signals_from_fetch,
)
from src.contact.forms import detect_contact_form
from src.contact.helpers import (
    google_maps_url,
    is_contact_page,
    normalize_absolute_url,
    normalize_email,
    normalize_phone,
)
from src.contact.jsonld import extract_jsonld
from src.contact.schema import ContactSignals, merge_contact_signals
from src.contact.social import classify_social_url, extract_social_urls

HOME = "https://acme.example.com/"


class TestJsonldExtraction(unittest.TestCase):
    def test_localbusiness_subtype_extracts_full_profile(self) -> None:
        data = extract_jsonld(JSONLD_HOMEPAGE)
        self.assertEqual(data["address"], "100 Main St, Austin, TX, 78701, US")
        self.assertEqual(data["postal_code"], "78701")
        self.assertEqual(data["country"], "US")
        self.assertEqual(data["owner_name"], "Bob Acme")
        self.assertEqual(data["opening_hours"], "Monday 09:00-17:00; Tuesday 09:00-17:00")
        self.assertEqual(data["service_areas"], ["Austin", "Round Rock"])
        self.assertIn("https://www.instagram.com/acmeplumbing", data["same_as"])
        self.assertEqual(data["telephone"], "+1-512-555-0100")
        self.assertEqual(data["email"], "office@acme.example.com")

    def test_graph_and_organization_node(self) -> None:
        data = extract_jsonld(GRAPH_PAGE)
        self.assertEqual(data["address"], "5 Oak Ave, Austin, 78702")
        self.assertEqual(data["postal_code"], "78702")
        self.assertEqual(data["telephone"], "+1-512-555-0199")
        self.assertEqual(data["email"], "info@acme.example.com")

    def test_empty_html_returns_empty(self) -> None:
        self.assertEqual(extract_jsonld(""), {})
        self.assertEqual(extract_jsonld("<html><body>no json</body></html>"), {})


class TestSocialExtraction(unittest.TestCase):
    def test_platforms_detected_and_normalized(self) -> None:
        found, ordered = extract_social_urls(SOCIALS_PAGE, HOME)
        self.assertEqual(found["facebook_url"], "https://www.facebook.com/acmepage")
        self.assertEqual(found["instagram_url"], "https://www.instagram.com/acmephotos")
        self.assertEqual(found["linkedin_url"], "https://www.linkedin.com/company/acme-plumbing")
        self.assertEqual(found["twitter_url"], "https://twitter.com/acmetweets")
        self.assertEqual(found["youtube_url"], "https://www.youtube.com/channel/UCabc123")
        self.assertEqual(found["whatsapp_url"], "https://wa.me/15125550100?text=hello")
        self.assertIn("https://fb.com/acmepage", ordered)

    def test_platform_chrome_ignored(self) -> None:
        self.assertIsNone(classify_social_url("https://www.linkedin.com/login"))
        self.assertIsNone(classify_social_url("https://x.com/intent/tweet?text=hi"))
        self.assertIsNone(classify_social_url("https://www.facebook.com/sharer/sharer.php"))

    def test_youtube_watch_link_ignored(self) -> None:
        self.assertIsNone(classify_social_url("https://www.youtube.com/watch?v=abc123"))

    def test_non_social_ignored(self) -> None:
        self.assertIsNone(classify_social_url("https://acme.example.com/services"))
        self.assertIsNone(classify_social_url("mailto:hello@example.com"))


class TestFormDetection(unittest.TestCase):
    def test_contact_form_action_resolved(self) -> None:
        url = detect_contact_form(CONTACT_FORM_PAGE, HOME, page_label="Contact")
        self.assertEqual(url, "https://acme.example.com/submit-contact")

    def test_login_form_ignored(self) -> None:
        self.assertIsNone(detect_contact_form(LOGIN_ONLY_PAGE, HOME, page_label="Contact"))

    def test_no_form_returns_none(self) -> None:
        self.assertIsNone(detect_contact_form(NO_FORM_PAGE, HOME))

    def test_contact_page_form_without_action_uses_page_url(self) -> None:
        html = '<html><body><form><input name="message"></form></body></html>'
        url = detect_contact_form(html, HOME, page_label="Contact")
        self.assertEqual(url, HOME)


class TestContactPageDetection(unittest.TestCase):
    def test_label_variants(self) -> None:
        for label in ("Contact", "contact-us", "CONTACTS"):
            self.assertTrue(is_contact_page(label, "https://acme.example.com/"))
        self.assertFalse(is_contact_page("Home", "https://acme.example.com/"))
        self.assertFalse(is_contact_page("About", "https://acme.example.com/"))

    def test_url_path_fallback(self) -> None:
        self.assertTrue(is_contact_page("Home", "https://acme.example.com/contact"))
        self.assertFalse(is_contact_page("Home", "https://acme.example.com/services"))


class TestHelpers(unittest.TestCase):
    def test_normalize_absolute_url(self) -> None:
        self.assertEqual(
            normalize_absolute_url("/contact", "https://acme.example.com/"),
            "https://acme.example.com/contact",
        )
        self.assertEqual(
            normalize_absolute_url(
                "https://fb.com/acme?utm_source=x&ref=y#frag", None
            ),
            "https://fb.com/acme",
        )

    def test_unsafe_urls_rejected(self) -> None:
        self.assertIsNone(normalize_absolute_url("javascript:alert(1)"))
        self.assertIsNone(normalize_absolute_url("mailto:x@example.com"))
        self.assertIsNone(normalize_absolute_url("data:text/html,hi"))
        self.assertIsNone(normalize_absolute_url(""))
        self.assertIsNone(normalize_absolute_url(None))

    def test_phone_email_reuse_pipeline_sanitizers(self) -> None:
        self.assertEqual(normalize_phone("Tel: +1-512-555-0100"), "+1-512-555-0100")
        self.assertEqual(normalize_phone("Call: +1 512 555 0100"), "+1 512 555 0100")
        self.assertEqual(normalize_phone("not-a-phone"), None)
        self.assertEqual(normalize_email("Reach bob@example.com today"), "bob@example.com")
        self.assertIsNone(normalize_email("no email here"))

    def test_google_maps_url_local(self) -> None:
        self.assertEqual(
            google_maps_url(30.2672, -97.7431),
            "https://www.google.com/maps/search/?api=1&query=30.267200,-97.743100",
        )
        self.assertIsNone(google_maps_url(None, -97.7431))
        self.assertIsNone(google_maps_url(30.2672, None))
        self.assertIsNone(google_maps_url(91.0, 0.0))


class TestMergePrecedence(unittest.TestCase):
    def test_first_non_empty_wins(self) -> None:
        first = ContactSignals(address="100 Main St", facebook_url="https://fb.com/a")
        second = ContactSignals(address="Other St", instagram_url="https://ig.com/a")
        merged = merge_contact_signals([first, second])
        self.assertEqual(merged.address, "100 Main St")
        self.assertEqual(merged.facebook_url, "https://fb.com/a")
        self.assertEqual(merged.instagram_url, "https://ig.com/a")

    def test_valid_value_never_overwritten_by_empty(self) -> None:
        first = ContactSignals(address="100 Main St")
        merged = merge_contact_signals([first, ContactSignals()])
        self.assertEqual(merged.address, "100 Main St")

    def test_lists_union_in_order(self) -> None:
        a = ContactSignals(service_areas=["Austin"], social_urls=["https://fb.com/a"])
        b = ContactSignals(service_areas=["Austin", "Dallas"], social_urls=["https://ig.com/b"])
        merged = merge_contact_signals([a, b])
        self.assertEqual(merged.service_areas, ["Austin", "Dallas"])
        self.assertEqual(merged.social_urls, ["https://fb.com/a", "https://ig.com/b"])


class TestExtractor(unittest.TestCase):
    def test_extract_contact_signals_full_page(self) -> None:
        signals = extract_contact_signals(JSONLD_HOMEPAGE, HOME, page_label="HOME")
        self.assertEqual(signals.owner_name, "Bob Acme")
        self.assertEqual(signals.address, "100 Main St, Austin, TX, 78701, US")
        self.assertEqual(signals.postal_code, "78701")
        self.assertEqual(signals.country, "US")
        self.assertEqual(signals.opening_hours, "Monday 09:00-17:00; Tuesday 09:00-17:00")
        self.assertEqual(signals.phone, "+1-512-555-0100")
        self.assertEqual(signals.email, "office@acme.example.com")
        self.assertEqual(signals.facebook_url, "https://www.facebook.com/acmeplumbing")
        self.assertEqual(signals.twitter_url, "https://x.com/acmeplumbing")
        self.assertEqual(signals.whatsapp_url, "https://wa.me/15125550100")
        self.assertEqual(signals.instagram_url, "https://www.instagram.com/acmeplumbing")
        self.assertEqual(signals.youtube_url, "https://www.youtube.com/@acmeplumbing")
        self.assertEqual(signals.service_areas, ["Austin", "Round Rock"])
        self.assertIn("https://www.facebook.com/acmeplumbing", signals.social_urls)
        self.assertIsNone(signals.contact_page_url)

    def test_contact_page_url_set_on_contact_page(self) -> None:
        signals = extract_contact_signals(SOCIALS_PAGE, HOME, page_label="Contact")
        self.assertEqual(signals.contact_page_url, HOME)

    def test_contact_form_url_set(self) -> None:
        signals = extract_contact_signals(CONTACT_FORM_PAGE, HOME, page_label="Contact")
        self.assertEqual(signals.contact_form_url, "https://acme.example.com/submit-contact")

    def test_empty_html_yields_empty_signals(self) -> None:
        signals = extract_contact_signals("", HOME, page_label="HOME")
        self.assertIsNone(signals.owner_name)
        self.assertEqual(signals.service_areas, [])
        self.assertEqual(signals.social_urls, [])

    def test_from_fetch_uses_final_url(self) -> None:
        fetch = _FakeFetch(JSONLD_HOMEPAGE, "https://acme.example.com/", "https://www.acme.example.com/")
        signals = extract_contact_signals_from_fetch(fetch)
        self.assertEqual(signals.postal_code, "78701")

    def test_from_crawl_aggregates_pages(self) -> None:
        class Page:
            def __init__(self, label: str, html: str, url: str) -> None:
                self.label = label
                self.html = html
                self.url = url
                self.contact = extract_contact_signals(html, url, page_label=label)

        class Crawl:
            def __init__(self) -> None:
                self.pages = [
                    Page("About", GRAPH_PAGE, "https://acme.example.com/about"),
                    Page("HOME", JSONLD_HOMEPAGE, HOME),
                ]

        signals = extract_contact_signals_from_crawl(Crawl())
        # Homepage wins for address (first non-empty in priority order).
        self.assertEqual(signals.address, "100 Main St, Austin, TX, 78701, US")
        self.assertIn("https://www.facebook.com/acmeplumbing", signals.social_urls)


class _FakeFetch:
    def __init__(self, html: str, url: str, final_url: str) -> None:
        self.html = html
        self.url = url
        self.final_url = final_url
        self.success = True
        self.text = html


if __name__ == "__main__":
    unittest.main()
