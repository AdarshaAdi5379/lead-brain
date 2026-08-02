import unittest

from src.scraping.content_extractor import (
    extract_contact_clues,
    parse_page,
)

PAGE = """<!DOCTYPE html>
<html>
<head>
  <title>Acme Plumbing</title>
  <meta name="description" content="Fast plumbers in Austin.">
  <link rel="canonical" href="https://acme.example.com/home">
</head>
<body>
  <header><nav><a href="/about">About</a><a href="/services">Services</a></nav></header>
  <div class="cookie-banner">We use cookies. Accept.</div>
  <div class="social"><a href="https://x.com/acme">X</a></div>
  <h1>Acme Plumbing</h1>
  <p>We fix <b>pipes</b> and water heaters in Austin, TX.</p>
  <h2>Why choose us</h2>
  <p>Licensed and insured since 1990.</p>
  <footer>© 2024 Acme. <a href="mailto:info@acme.com">Email</a> <a href="tel:+1-512-555-0100">Call</a></footer>
</body>
</html>
"""


class TestContentExtractor(unittest.TestCase):
    def test_title_meta_canonical(self) -> None:
        page = parse_page(PAGE, "https://acme.example.com/")
        self.assertEqual(page.title, "Acme Plumbing")
        self.assertEqual(page.meta_description, "Fast plumbers in Austin.")
        self.assertEqual(page.canonical_url, "https://acme.example.com/home")

    def test_boilerplate_removed(self) -> None:
        page = parse_page(PAGE, "https://acme.example.com/")
        self.assertNotIn("Cookie", page.text)
        self.assertNotIn("About", page.text)
        self.assertNotIn("Services", page.text)
        self.assertNotIn("©", page.text)
        self.assertNotIn("info@acme.example.com", page.text)

    def test_content_is_kept(self) -> None:
        page = parse_page(PAGE, "https://acme.example.com/")
        self.assertIn("We fix pipes and water heaters", page.text)

    def test_headings_extracted(self) -> None:

        page = parse_page(PAGE, "https://acme.example.com/")
        levels = [h.level for h in page.headings]
        texts = [h.text for h in page.headings]
        self.assertIn("Acme Plumbing", texts)
        self.assertEqual(len(levels), 2)

    def test_word_count(self) -> None:
        page = parse_page(PAGE, "https://acme.example.com/")
        self.assertGreater(page.word_count, 0)


class TestContactClues(unittest.TestCase):
    def test_mailto_and_tel_captured(self) -> None:
        clues = extract_contact_clues(PAGE, "https://acme.example.com/")
        joined = "\n".join(clues)
        self.assertIn("email: info@acme.com", joined)
        # The footer tel: link survives as a phone hint.
        self.assertIn("+1-512-555-0100", joined)

    def test_dedupes_emails(self) -> None:
        html = (
            '<a href="mailto:bob@x.com">b</a>'
            '<span>bob@x.com</span>'
            '<a href="mailto:bob@x.com">again</a>'
        )
        clues = extract_contact_clues(html, "https://acme.example.com/")
        emails = [c for c in clues if c.startswith("email: bob@x.com")]
        self.assertEqual(len(emails), 1)


if __name__ == "__main__":
    unittest.main()