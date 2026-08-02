import unittest

from src.scraping.content_merger import Section, merge_sections, trim_text
from src.scraping.page_cache import content_hash


class TestTrimText(unittest.TestCase):
    def test_short_text_unchanged(self) -> None:
        self.assertEqual(trim_text("hello", max_chars=2000), "hello")

    def test_at_limit_unchanged(self) -> None:
        self.assertEqual(trim_text("x" * 100, max_chars=100), "x" * 100)

    def test_prefers_paragraph_boundary(self) -> None:
        text = "A" * 25 + "\n\n" + "B" * 40
        trimmed = trim_text(text, max_chars=40)
        self.assertEqual(trimmed, "A" * 25)

    def test_never_splits_a_word(self) -> None:
        text = "one two three four five"
        trimmed = trim_text(text, max_chars=10)
        self.assertEqual(trimmed, "one two")

    def test_boundary_fallback_to_single_line_break(self) -> None:
        text = "A" * 25 + "\n" + "B" * 40
        trimmed = trim_text(text, max_chars=40)
        self.assertEqual(trimmed, "A" * 25)


class TestMergeSections(unittest.TestCase):
    def test_home_first_and_labelled(self) -> None:
        merged = merge_sections(
            [
                Section(label="HOME", url="https://acme.example.com/", text="Home copy."),
                Section(label="About", url="https://acme.example.com/about", text="Our story."),
            ]
        )
        self.assertIn("HOME", merged)
        self.assertIn("https://acme.example.com/about", merged)
        self.assertIn("Our story.", merged)
        self.assertIn("=" * 17, merged)
        # Home appears before About.
        self.assertLess(merged.index("HOME"), merged.index("About"))

    def test_empty_pages_ok(self) -> None:
        merged = merge_sections([])
        self.assertEqual(merged, "")


class TestContentHash(unittest.TestCase):
    def test_deterministic(self) -> None:
        self.assertEqual(content_hash("abc"), content_hash("abc"))
        self.assertNotEqual(content_hash("abc"), content_hash("abd"))


if __name__ == "__main__":
    unittest.main()