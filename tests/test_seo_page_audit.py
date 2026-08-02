import unittest

from src.seo.base import Severity
from src.seo.page_audit import audit_page, audit_page_from_text
from src.seo.parser import extract_evidence

LONG_TEXT = " ".join(["word"] * 400)

GOOD_HTML = f"""
<html>
<head>
  <title>Acme Plumbing | Local Plumbers</title>
  <meta name="description" content="{"d" * 130}">
  <link rel="canonical" href="https://example.com/">
  <meta name="viewport" content="width=device-width">
  <meta property="og:title" content="Acme Plumbing">
  <meta property="og:description" content="Local plumbers">
  <meta name="twitter:card" content="summary">
  <link rel="icon" href="/favicon.ico">
  <script type="application/ld+json">{{"@type": "LocalBusiness"}}</script>
</head>
<body itemscope itemtype="https://schema.org/LocalBusiness">
  <h1>Acme Plumbing</h1>
  <h2>Services</h2>
  <p>{LONG_TEXT}</p>
  <a href="/about">About</a><a href="/services">Services</a><a href="/contact">Contact</a>
  <img src="/a.jpg" alt="An image">
</body>
</html>
"""


class TestPageAudit(unittest.TestCase):
    def test_audit_page_fields(self) -> None:
        audit = audit_page(
            extract_evidence(GOOD_HTML, "https://example.com/", is_homepage=True),
            is_homepage=True,
        )
        self.assertTrue(audit.html_available)
        self.assertTrue(audit.title_present)
        self.assertTrue(audit.meta_description_present)
        self.assertEqual(audit.h1_count, 1)
        self.assertTrue(audit.canonical_present)
        self.assertTrue(audit.robots_meta is False)
        self.assertTrue(audit.viewport_present)
        self.assertFalse(audit.noindex)
        self.assertFalse(audit.nofollow)
        self.assertGreaterEqual(audit.word_count, 400)
        self.assertEqual(audit.image_count, 1)
        self.assertEqual(audit.images_missing_alt_count, 0)
        self.assertTrue(audit.json_ld_present)
        self.assertTrue(audit.schema_present)
        self.assertEqual(audit.internal_link_count, 3)
        self.assertEqual(audit.issues, ())
        self.assertEqual(audit.score, 100)
        self.assertEqual(audit.health, "Excellent")
        self.assertEqual(audit.page_type, "home")

    def test_audit_page_reports_noindex(self) -> None:
        html = (
            "<html><head><title>Page</title>"
            '<meta name="robots" content="noindex">'
            "</head><body></body></html>"
        )
        audit = audit_page(extract_evidence(html, "https://example.com/"))
        self.assertTrue(audit.noindex)
        self.assertFalse(audit.nofollow)
        self.assertTrue(any(i.code == "noindex" for i in audit.issues))

    def test_text_only_audit_is_never_falsely_missing(self) -> None:
        audit = audit_page_from_text("https://example.com/about", word_count=120)
        self.assertFalse(audit.html_available)
        self.assertFalse(audit.title_present)
        self.assertEqual(audit.word_count, 120)
        self.assertEqual(audit.score, 100)
        self.assertEqual(audit.health, "Excellent")
        self.assertEqual(len(audit.issues), 1)
        self.assertEqual(audit.issues[0].severity, Severity.INFO)

    def test_to_dict_contains_issues_json(self) -> None:
        audit = audit_page(extract_evidence("<html><body><p>tiny</p></body></html>", "https://example.com/"))
        data = audit.to_dict()
        self.assertIn("issues_json", data)
        self.assertIn("score", data)
        self.assertIn("url", data)


if __name__ == "__main__":
    unittest.main()
