import unittest
from types import SimpleNamespace

from src.seo.site_audit import WellKnownProbe, audit_site

LONG_TEXT = " ".join(["word"] * 400)


def _good_page(url: str, *, homepage: bool = False) -> SimpleNamespace:
    title = "Acme Plumbing | Local Plumbers" if homepage else "Acme Plumbing | " + url.split("/")[-1]
    html = (
        "<html><head>"
        f"<title>{title}</title>"
        f'<meta name="description" content="{"d" * 120}{url}">'
        '<link rel="canonical" href="' + url + '">'
        '<meta name="viewport" content="width=device-width">'
        "</head><body>"
        "<h1>Acme Plumbing</h1><h2>Services</h2>"
        f"<p>{LONG_TEXT}</p>"
        '<a href="/about">About</a><a href="/services">Services</a>'
        '<a href="/contact">Contact</a>'
        '<img src="/a.jpg" alt="An image">'
        "</body></html>"
    )
    return SimpleNamespace(url=url, label="PAGE", title=title, text=LONG_TEXT, html=html)


def _poor_page(url: str) -> SimpleNamespace:
    return SimpleNamespace(
        url=url,
        label="PAGE",
        title="",
        text="tiny",
        html="<html><head></head><body><p>tiny</p></body></html>",
    )


def _text_only_page(url: str) -> SimpleNamespace:
    return SimpleNamespace(url=url, label="PAGE", title="", text="some words here", html="")


class TestSiteAudit(unittest.TestCase):
    def test_aggregates_counts_over_html_pages(self) -> None:
        pages = [
            _good_page("https://example.com/", homepage=True),
            _good_page("https://example.com/about"),
            _good_page("https://example.com/contact"),
        ]
        audit = audit_site(pages, "https://example.com/")

        self.assertEqual(audit.total_pages_audited, 3)
        self.assertEqual(audit.html_pages, 3)
        self.assertEqual(audit.pages_with_title, 3)
        self.assertEqual(audit.pages_with_meta_description, 3)
        self.assertEqual(audit.pages_with_h1, 3)
        self.assertEqual(audit.pages_with_multiple_h1, 0)
        self.assertEqual(audit.pages_with_noindex, 0)
        self.assertEqual(audit.pages_with_canonical, 3)
        self.assertEqual(audit.pages_with_json_ld, 0)
        self.assertEqual(audit.pages_with_images_missing_alt, 0)
        self.assertEqual(audit.pages_with_thin_content, 0)
        self.assertEqual(audit.pages_with_duplicate_titles, 0)
        self.assertEqual(audit.pages_with_duplicate_descriptions, 0)
        self.assertEqual(len(audit.pages), 3)

    def test_site_score_reflects_page_scores_and_site_issues(self) -> None:
        pages = [
            _good_page("https://example.com/", homepage=True),
            _poor_page("https://example.com/about"),
            _good_page("https://example.com/contact"),
        ]
        audit = audit_site(pages, "https://example.com/")

        self.assertLess(audit.site_score, 100)
        self.assertGreater(audit.site_score, 0)
        page_scores = [page.score for page in audit.pages]
        self.assertLess(audit.site_score, round(sum(page_scores) / len(page_scores)) + 1)
        self.assertTrue(any(i.code == "no_services_page" for i in audit.severity_summary))
        self.assertFalse(audit.robots_txt_detected)
        self.assertFalse(audit.sitemap_detected)

    def test_duplicate_titles_and_descriptions_detected(self) -> None:
        def _page(url: str, title: str, description: str) -> SimpleNamespace:
            html = (
                "<html><head>"
                f"<title>{title}</title>"
                f'<meta name="description" content="{description}">'
                "</head><body><h1>H</h1><h2>H2</h2>"
                f"<p>{LONG_TEXT}</p>"
                '<a href="/a">A</a><a href="/b">B</a><a href="/c">C</a>'
                "</body></html>"
            )
            return SimpleNamespace(url=url, label="PAGE", title=title, text=LONG_TEXT, html=html)

        pages = [
            _page("https://example.com/", "Same Title", "d" * 130),
            _page("https://example.com/about", "Same Title", "d" * 130),
            _page("https://example.com/contact", "Other Title", "e" * 130),
        ]
        audit = audit_site(pages, "https://example.com/")

        self.assertEqual(audit.pages_with_duplicate_titles, 2)
        self.assertEqual(audit.pages_with_duplicate_descriptions, 2)
        self.assertTrue(any(i.code == "duplicate_titles" for i in audit.severity_summary))

    def test_robots_and_sitemap_detected_from_homepage_html(self) -> None:
        html = (
            "<html><head><title>Acme</title>"
            '<link rel="sitemap" type="application/xml" href="/sitemap.xml">'
            "</head><body><p>See /robots.txt.</p></body></html>"
        )
        pages = [
            SimpleNamespace(url="https://example.com/", label="HOME", title="Acme", text="x", html=html),
        ]
        audit = audit_site(pages, "https://example.com/")
        self.assertTrue(audit.robots_txt_detected)
        self.assertTrue(audit.sitemap_detected)

    def test_probe_merges_with_html_detection(self) -> None:
        pages = [
            SimpleNamespace(url="https://example.com/", label="HOME", title="Acme", text="x",
                            html="<html><head><title>Acme</title></head><body></body></html>"),
        ]
        probe = WellKnownProbe(
            robots_url="https://example.com/robots.txt",
            sitemap_url="https://example.com/sitemap.xml",
            robots_txt_found=True,
            sitemap_found=False,
            sitemap_in_robots=True,
        )
        audit = audit_site(pages, "https://example.com/", probe=probe)
        self.assertTrue(audit.robots_txt_detected)
        self.assertTrue(audit.sitemap_detected)

    def test_text_only_pages_excluded_from_html_aggregates(self) -> None:
        pages = [
            _good_page("https://example.com/", homepage=True),
            _text_only_page("https://example.com/legacy-cached"),
        ]
        audit = audit_site(pages, "https://example.com/")

        self.assertEqual(audit.total_pages_audited, 2)
        self.assertEqual(audit.html_pages, 1)
        self.assertEqual(audit.pages_with_title, 1)
        self.assertEqual(audit.html_pages - audit.pages_with_title, 0)

    def test_empty_pages_yield_zero_audit(self) -> None:
        audit = audit_site([], "https://example.com/")
        self.assertEqual(audit.total_pages_audited, 0)
        self.assertEqual(audit.site_score, 100)


if __name__ == "__main__":
    unittest.main()
