import unittest

from src.scraping.link_extractor import extract_internal_links, normalize_page_url

HOME = "https://acme.example.com/"


def _html(body: str) -> str:
    return f"<html><body>{body}</body></html>"


class TestInternalLinks(unittest.TestCase):
    def test_keeps_same_domain_and_resolves_relative(self) -> None:
        html = _html(
            '<a href="/about">About</a><a href="services">Services</a>'
        )
        links = extract_internal_links(html, HOME)
        urls = [link.url for link in links]
        self.assertIn("https://acme.example.com/about", urls)
        self.assertIn("https://acme.example.com/services", urls)

    def test_filters_external_domains(self) -> None:
        html = _html(
            '<a href="https://other.example.com/">Out</a>'
            '<a href="https://acme.example.com/news">In</a>'
        )
        links = extract_internal_links(html, HOME)
        self.assertEqual([l.url for l in links], ["https://acme.example.com/news"])

    def test_filters_mailto_tel_javascript_data(self) -> None:
        html = _html(
            '<a href="mailto:a@b.com">mail</a>'
            '<a href="tel:+123">call</a>'
            '<a href="javascript:void(0)">js</a>'
            '<a href="data:text/html,hi">dump</a>'
            '<a href="/ok">ok</a>'
        )
        links = extract_internal_links(html, HOME)
        self.assertEqual([l.url for l in links], ["https://acme.example.com/ok"])

    def test_filters_asset_extensions(self) -> None:
        html = _html(
            '<a href="/file.pdf">pdf</a>'
            '<a href="/img/logo.png">png</a>'
            '<a href="/app.min.css">css</a>'
            '<a href="/bundle.js">js</a>'
            '<a href="/package.zip">zip</a>'
            '<a href="/real">real</a>'
        )
        links = extract_internal_links(html, HOME)
        self.assertEqual([l.url for l in links], ["https://acme.example.com/real"])

    def test_pure_fragment_links_ignored(self) -> None:
        html = _html('<a href="#top">top</a><a href="/about#team">about</a>')
        links = extract_internal_links(html, HOME)
        self.assertEqual([l.url for l in links], ["https://acme.example.com/about"])

    def test_removes_duplicates(self) -> None:
        html = _html(
            '<a href="/about">first</a><a href="/about/">second</a>'
            '<a href="/About">third</a><a href="/about?x=1">fourth</a>'
        )
        links = extract_internal_links(html, HOME)
        self.assertEqual(len(links), 1)
        self.assertEqual(links[0].url, "https://acme.example.com/about")

    def test_anchor_text_preserved(self) -> None:
        html = _html('<a href="/about">  About <b>Us</b></a>')
        links = extract_internal_links(html, HOME)
        self.assertEqual(links[0].text, "About Us")

    def test_www_host_alias_is_internal(self) -> None:
        html = _html('<a href="https://www.acme.example.com/about">w</a>')
        links = extract_internal_links(html, HOME)
        self.assertEqual(len(links), 1)


class TestUrlNormalization(unittest.TestCase):
    def test_strips_fragment_query_and_trailing_slash(self) -> None:
        self.assertEqual(
            normalize_page_url("https://Foo.com/About/?x=1#top"),
            "https://foo.com/about",
        )

    def test_root_path_preserved(self) -> None:
        self.assertEqual(normalize_page_url("https://foo.com"), "https://foo.com/")


if __name__ == "__main__":
    unittest.main()