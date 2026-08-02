import unittest

from src.seo.parser import extract_evidence

LONG_TEXT = " ".join(["word"] * 400)

GOOD_HTML = f"""
<!doctype html>
<html>
<head>
  <title>Acme Plumbing | Fast Local Plumbers</title>
  <meta name="description" content="Acme Plumbing provides 24/7 plumbing services across Austin with licensed plumbers, upfront pricing and same-day appointments.">
  <link rel="canonical" href="https://www.acme.example.com/">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="robots" content="index, follow">
  <meta property="og:title" content="Acme Plumbing">
  <meta property="og:description" content="24/7 local plumbers in Austin">
  <meta name="twitter:card" content="summary">
  <link rel="icon" href="/favicon.ico">
  <script type="application/ld+json">{{"@type": "LocalBusiness"}}</script>
</head>
<body itemscope itemtype="https://schema.org/LocalBusiness">
  <h1>Acme Plumbing</h1>
  <h2>Our services</h2>
  <h2>Why choose us</h2>
  <p>{LONG_TEXT}</p>
  <a href="/about">About us</a>
  <a href="/contact">Contact</a>
  <a href="/services">Services</a>
  <a href="https://external.example.com/">External</a>
  <a href="mailto:info@acme.example.com">Email</a>
  <img src="/hero.jpg" alt="Plumber at work">
  <img src="/team.jpg" alt="The team">
</body>
</html>
"""

BROKEN_HTML = """
<!doctype html>
<html>
<head>
  <title>Broken site</title>
  <meta name="robots" content="noindex, nofollow">
</head>
<body>
  <h1>First heading</h1>
  <h1>Second heading</h1>
  <p>Some short text here.</p>
  <img src="/img1.png">
  <img src="/img2.png" alt="">
  <img>
  <a href="/only-one">Only link</a>
</body>
</html>
"""


class TestSeoParser(unittest.TestCase):
    def test_extracts_all_good_signals(self) -> None:
        evidence = extract_evidence(GOOD_HTML, "https://www.acme.example.com/", is_homepage=True)

        self.assertEqual(evidence.title, "Acme Plumbing | Fast Local Plumbers")
        self.assertTrue(evidence.meta_description)
        self.assertEqual(evidence.canonical_url, "https://www.acme.example.com/")
        self.assertEqual(evidence.robots_meta, "index, follow")
        self.assertTrue(evidence.viewport_present)
        self.assertEqual(evidence.h1_count, 1)
        self.assertEqual(evidence.h2_count, 2)
        self.assertTrue(evidence.is_https)
        self.assertTrue(evidence.json_ld_present)
        self.assertTrue(evidence.schema_present)
        self.assertTrue(evidence.og_title_present)
        self.assertTrue(evidence.og_description_present)
        self.assertTrue(evidence.twitter_card_present)
        self.assertTrue(evidence.favicon_present)
        self.assertEqual(evidence.image_count, 2)
        self.assertEqual(evidence.images_missing_alt_count, 0)
        self.assertEqual(evidence.images_broken_count, 0)
        self.assertEqual(evidence.internal_link_count, 3)
        self.assertEqual(evidence.mixed_content_count, 0)
        self.assertGreaterEqual(evidence.word_count, 400)
        self.assertEqual(evidence.page_type, "home")

    def test_missing_signals_are_reported(self) -> None:
        evidence = extract_evidence(BROKEN_HTML, "http://example.com/broken")

        self.assertEqual(evidence.title, "Broken site")
        self.assertEqual(evidence.meta_description, "")
        self.assertIsNone(evidence.canonical_url)
        self.assertFalse(evidence.viewport_present)
        self.assertFalse(evidence.is_https)
        self.assertEqual(evidence.h1_count, 2)
        self.assertIn("noindex", evidence.robots_meta.lower())
        self.assertIn("nofollow", evidence.robots_meta.lower())
        self.assertEqual(evidence.images_missing_alt_count, 3)
        self.assertEqual(evidence.images_broken_count, 1)
        self.assertEqual(evidence.internal_link_count, 1)
        self.assertFalse(evidence.json_ld_present)
        self.assertFalse(evidence.schema_present)
        self.assertFalse(evidence.og_title_present)
        self.assertFalse(evidence.og_description_present)
        self.assertFalse(evidence.twitter_card_present)

    def test_mixed_content_detected_on_https_page(self) -> None:
        html = (
            '<html><head><title>Mixed</title></head><body>'
            '<p>Body text content for the page.</p>'
            '<img src="http://cdn.example.com/pic.jpg">'
            '<script src="http://cdn.example.com/app.js"></script>'
            '</body></html>'
        )
        evidence = extract_evidence(html, "https://example.com/")
        self.assertGreaterEqual(evidence.mixed_content_count, 2)

    def test_http_page_is_not_https(self) -> None:
        html = "<html><head><title>Old</title></head><body><p>Body</p></body></html>"
        evidence = extract_evidence(html, "http://example.com/")
        self.assertFalse(evidence.is_https)

    def test_canonical_is_resolved_to_absolute(self) -> None:
        html = (
            '<html><head><title>Rel</title>'
            '<link rel="canonical" href="/canonical-page">'
            "</head><body></body></html>"
        )
        evidence = extract_evidence(html, "https://example.com/somewhere")
        self.assertEqual(evidence.canonical_url, "https://example.com/canonical-page")

    def test_page_type_inference(self) -> None:
        cases = {
            "https://example.com/contact": "contact",
            "https://example.com/about-us": "about",
            "https://example.com/services": "services",
            "https://example.com/random-page": "other",
        }
        for url, expected in cases.items():
            evidence = extract_evidence("<html><body></body></html>", url)
            self.assertEqual(evidence.page_type, expected, url)

    def test_robots_and_sitemap_references(self) -> None:
        html = (
            '<html><head><title>Refs</title>'
            '<link rel="sitemap" type="application/xml" href="/sitemap.xml">'
            "</head><body><p>See /robots.txt for crawler rules.</p></body></html>"
        )
        evidence = extract_evidence(html, "https://example.com/")
        self.assertTrue(evidence.sitemap_reference)
        self.assertTrue(evidence.robots_txt_reference)


if __name__ == "__main__":
    unittest.main()
