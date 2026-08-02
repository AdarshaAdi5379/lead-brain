import unittest

from src.seo.base import Severity
from src.seo.parser import extract_evidence
from src.seo.rules import page_issues

LONG_TEXT = " ".join(["word"] * 400)


def _evidence(html: str, url: str = "https://example.com/", *, homepage: bool = False):
    return extract_evidence(html, url, is_homepage=homepage)


def _issue_codes(issues):
    return {issue.code for issue in issues}


class TestSeoRules(unittest.TestCase):
    def test_clean_page_scores_full_marks(self) -> None:
        html = (
            "<html><head>"
            "<title>Acme Plumbing | Local Plumbers</title>"
            '<meta name="description" content="' + "d" * 130 + '">'
            '<link rel="canonical" href="https://example.com/">'
            '<meta name="viewport" content="width=device-width">'
            '<meta property="og:title" content="Acme Plumbing">'
            '<meta property="og:description" content="Local plumbers">'
            '<meta name="twitter:card" content="summary">'
            '<link rel="icon" href="/favicon.ico">'
            '<script type="application/ld+json">{}</script>'
            "</head><body itemscope itemtype='https://schema.org/LocalBusiness'>"
            "<h1>Acme Plumbing</h1><h2>Services</h2>"
            f"<p>{LONG_TEXT}</p>"
            '<a href="/about">About</a><a href="/services">Services</a>'
            '<a href="/contact">Contact</a>'
            '<img src="/a.jpg" alt="An image">'
            "</body></html>"
        )
        issues, score = page_issues(_evidence(html))
        self.assertEqual(score, 100)
        self.assertEqual(issues, [])

    def test_missing_title_is_critical_and_punished(self) -> None:
        html = (
            "<html><head>"
            '<meta name="description" content="' + "d" * 130 + '">'
            "</head><body><h1>Only heading</h1></body></html>"
        )
        issues, score = page_issues(_evidence(html))
        self.assertIn("missing_title", _issue_codes(issues))
        title_issue = next(i for i in issues if i.code == "missing_title")
        self.assertEqual(title_issue.severity, Severity.CRITICAL)
        self.assertLess(score, 100)

    def test_title_length_checks_only_apply_when_title_present(self) -> None:
        short_html = (
            "<html><head><title>Short</title></head><body></body></html>"
        )
        issues, _ = page_issues(_evidence(short_html))
        self.assertIn("title_too_short", _issue_codes(issues))
        self.assertNotIn("missing_title", _issue_codes(issues))

        long_title = "<title>" + "t" * 80 + "</title>"
        issues, _ = page_issues(_evidence(f"<html><head>{long_title}</head><body></body></html>"))
        self.assertIn("title_too_long", _issue_codes(issues))

    def test_multiple_h1_and_missing_h1(self) -> None:
        no_h1 = "<html><head><title>Page</title></head><body><p>Text</p></body></html>"
        issues, _ = page_issues(_evidence(no_h1))
        self.assertIn("missing_h1", _issue_codes(issues))

        two_h1 = (
            "<html><head><title>Page</title></head><body>"
            "<h1>One</h1><h1>Two</h1></body></html>"
        )
        issues, _ = page_issues(_evidence(two_h1))
        self.assertIn("multiple_h1", _issue_codes(issues))

    def test_noindex_and_nofollow_detected(self) -> None:
        html = (
            "<html><head><title>Page</title>"
            '<meta name="robots" content="noindex, nofollow">'
            "</head><body></body></html>"
        )
        issues, _ = page_issues(_evidence(html))
        self.assertIn("noindex", _issue_codes(issues))
        self.assertIn("nofollow", _issue_codes(issues))

    def test_thin_content_threshold(self) -> None:
        thin = "<html><head><title>Page</title></head><body><p>Few words only.</p></body></html>"
        issues, _ = page_issues(_evidence(thin))
        self.assertIn("thin_content", _issue_codes(issues))

        rich = f"<html><head><title>Page</title></head><body><p>{LONG_TEXT}</p></body></html>"
        issues, _ = page_issues(_evidence(rich))
        self.assertNotIn("thin_content", _issue_codes(issues))

    def test_homepage_thin_bar_is_more_lenient(self) -> None:
        medium = f"<html><head><title>Page</title></head><body><p>{'w ' * 200}</p></body></html>"
        issues_normal, _ = page_issues(_evidence(medium))
        issues_home, _ = page_issues(_evidence(medium, homepage=True))
        self.assertIn("thin_content", _issue_codes(issues_normal))
        self.assertNotIn("thin_content", _issue_codes(issues_home))

    def test_missing_alt_ratio_penalties(self) -> None:
        half_missing = (
            "<html><head><title>Page</title></head><body>"
            '<img src="/a.jpg" alt="ok"><img src="/b.jpg">'
            "</body></html>"
        )
        issues, _ = page_issues(_evidence(half_missing))
        self.assertIn("images_missing_alt", _issue_codes(issues))

        all_missing = (
            "<html><head><title>Page</title></head><body>"
            '<img src="/a.jpg"><img src="/b.jpg">'
            "</body></html>"
        )
        issues, _ = page_issues(_evidence(all_missing))
        self.assertIn("images_missing_alt", _issue_codes(issues))

    def test_canonical_issues(self) -> None:
        missing = "<html><head><title>Page</title></head><body></body></html>"
        issues, _ = page_issues(_evidence(missing))
        self.assertIn("missing_canonical", _issue_codes(issues))

        cross_domain = (
            "<html><head><title>Page</title>"
            '<link rel="canonical" href="https://other.example.com/">'
            "</head><body></body></html>"
        )
        issues, _ = page_issues(_evidence(cross_domain))
        self.assertIn("canonical_cross_domain", _issue_codes(issues))

    def test_score_clamps_at_zero(self) -> None:
        html = (
            "<html><head>"
            '<meta name="robots" content="noindex">'
            "</head><body><p>tiny</p></body></html>"
        )
        issues, score = page_issues(_evidence(html, url="http://example.com/"))
        self.assertGreater(len(issues), 4)
        self.assertEqual(score, 0)

    def test_score_clamps_at_100(self) -> None:
        html = (
            "<html><head><title>The Perfectly Optimized Homepage Title</title>"
            '<meta name="description" content="' + "d" * 130 + '">'
            '<link rel="canonical" href="https://example.com/">'
            '<meta name="viewport" content="width=device-width">'
            '<meta property="og:title" content="Perfect">'
            '<meta property="og:description" content="Perfect page">'
            '<meta name="twitter:card" content="summary">'
            '<script type="application/ld+json">{}</script>'
            "</head><body itemscope itemtype='https://schema.org/LocalBusiness'>"
            "<h1>H</h1><h2>H2</h2>"
            f"<p>{LONG_TEXT}</p>"
            '<a href="/a">A</a><a href="/b">B</a><a href="/c">C</a>'
            "</body></html>"
        )
        _, score = page_issues(_evidence(html))
        self.assertEqual(score, 100)

if __name__ == "__main__":
    unittest.main()
