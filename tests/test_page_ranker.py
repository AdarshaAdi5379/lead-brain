import unittest

from src.scraping.link_extractor import Link
from src.scraping.page_ranker import (
    IGNORE_KEYWORDS,
    PRIORITY_KEYWORDS,
    find_contact_links,
    label_for_link,
    rank_pages,
    score_link,
    select_pages,
)


def _link(path: str, text: str = "") -> Link:
    return Link(url=f"https://acme.example.com{path}", text=text)


class TestScoreLink(unittest.TestCase):
    def test_priority_keywords_boost(self) -> None:
        self.assertGreater(score_link(_link("/about")), 0)
        self.assertGreater(score_link(_link("/services")), 0)
        self.assertGreater(score_link(_link("/contact-us")), 0)

    def test_ignore_keywords_score_negative(self) -> None:
        for path in ("/privacy", "/terms", "/login", "/checkout", "/cart", "/sitemap"):
            self.assertLess(score_link(_link(path)), 0, path)

    def test_anchor_text_adds_signal(self) -> None:
        self.assertGreater(
            score_link(_link("/something", text="See our Services")),
            score_link(_link("/something", text="Click")),
        )

    def test_blog_archives_are_ignored(self) -> None:
        self.assertIn("blog", IGNORE_KEYWORDS)
        self.assertLess(score_link(_link("/blog/2024/what-is-hvac")), 0)

    def test_about_keyword_present(self) -> None:
        self.assertIn("about", PRIORITY_KEYWORDS)


class TestRankAndSelect(unittest.TestCase):
    def test_deterministic_ranking(self) -> None:
        links = [
            _link("/contact"),
            _link("/privacy"),
            _link("/about"),
            _link("/services"),
        ]
        self.assertEqual(rank_pages(links), rank_pages(links))

    def test_top_pages_selected_first(self) -> None:
        links = [
            _link("/about"),
            _link("/services"),
            _link("/privacy"),
            _link("/login"),
            _link("/portfolio"),
        ]
        selection = select_pages(links, max_pages=3)
        urls = [link.url for link in selection.selected]
        self.assertIn("https://acme.example.com/about", urls)
        self.assertIn("https://acme.example.com/services", urls)
        self.assertIn("https://acme.example.com/portfolio", urls)
        skipped = " ".join(link.url for link in selection.skipped)
        self.assertIn("privacy", skipped)
        self.assertIn("login", skipped)

    def test_max_pages_cap(self) -> None:
        links = [
            _link("/about"),
            _link("/services"),
            _link("/products"),
            _link("/portfolio"),
            _link("/contact"),
            _link("/team"),
        ]
        selection = select_pages(links, max_pages=2)
        self.assertEqual(len(selection.selected), 2)

    def test_no_limit_returns_all_candidates(self) -> None:
        links = [_link("/about"), _link("/services"), _link("/privacy")]
        selection = select_pages(links, max_pages=10)
        self.assertEqual(len(selection.selected), 2)  # privacy skipped

    def test_zero_max_pages_selects_none(self) -> None:
        selection = select_pages([_link("/about")], max_pages=0)
        self.assertEqual(selection.selected, [])


class TestFindContactLinks(unittest.TestCase):
    def test_path_variants(self) -> None:
        links = [
            _link("/about"),
            _link("/contact"),
            _link("/contact-us"),
            _link("/get-in-touch"),
            _link("/team"),
        ]
        found = [link.url for link in find_contact_links(links)]
        self.assertEqual(
            found,
            [
                "https://acme.example.com/contact",
                "https://acme.example.com/contact-us",
                "https://acme.example.com/get-in-touch",
            ],
        )

    def test_anchor_text_variants(self) -> None:
        links = [
            _link("/reach-us", text="Contact Us"),
            _link("/about", text="About"),
            _link("/write-us", text="Get in Touch"),
        ]
        found = [link.url for link in find_contact_links(links)]
        self.assertEqual(
            found,
            [
                "https://acme.example.com/reach-us",
                "https://acme.example.com/write-us",
            ],
        )

    def test_no_contact_links(self) -> None:
        self.assertEqual(find_contact_links([_link("/about"), _link("/team")]), [])

    def test_preserves_original_order(self) -> None:
        links = [
            _link("/contact"),
            _link("/services"),
            _link("/contact-us"),
        ]
        found = [link.url for link in find_contact_links(links)]
        self.assertEqual(
            found,
            [
                "https://acme.example.com/contact",
                "https://acme.example.com/contact-us",
            ],
        )


class TestLabel(unittest.TestCase):
    def test_uses_anchor_text(self) -> None:
        self.assertEqual(label_for_link(_link("/about", "About Us")), "About Us")

    def test_derives_label_from_path(self) -> None:
        self.assertEqual(label_for_link(_link("/case-studies")), "Case Studies")


if __name__ == "__main__":
    unittest.main()