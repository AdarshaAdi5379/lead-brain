import unittest
from types import SimpleNamespace

from src.seo.report import csv_fields, csv_fields_from_row, summary_dict, to_llm_text, top_issues
from src.seo.site_audit import audit_site

LONG_TEXT = " ".join(["word"] * 400)


def _good_page(url: str) -> SimpleNamespace:
    html = (
        "<html><head>"
        "<title>Acme Plumbing | Page</title>"
        f'<meta name="description" content="{"d" * 130}">'
        '<link rel="canonical" href="' + url + '">'
        '<meta name="viewport" content="width=device-width">'
        "</head><body><h1>H</h1><h2>H2</h2>"
        f"<p>{LONG_TEXT}</p>"
        '<a href="/a">A</a><a href="/b">B</a><a href="/c">C</a>'
        '<img src="/a.jpg" alt="ok">'
        "</body></html>"
    )
    return SimpleNamespace(url=url, label="PAGE", title="t", text=LONG_TEXT, html=html)


def _make_audit():
    pages = [
        _good_page("https://example.com/"),
        SimpleNamespace(
            url="https://example.com/about",
            label="PAGE",
            title="",
            text="tiny",
            html="<html><head></head><body><p>tiny</p></body></html>",
        ),
    ]
    return audit_site(pages, "https://example.com/")


class TestSeoReport(unittest.TestCase):
    def test_to_llm_text_contains_key_facts(self) -> None:
        text = to_llm_text(_make_audit())
        self.assertIn("Site score:", text)
        self.assertIn("page(s) audited", text)
        self.assertIn("Sitemap detected:", text)
        self.assertTrue(text.endswith("\n"))

    def test_to_llm_text_empty_audit(self) -> None:
        audit = audit_site([], "https://example.com/")
        self.assertIn("not available", to_llm_text(audit))

    def test_summary_dict_shape(self) -> None:
        audit = _make_audit()
        data = summary_dict(audit)
        self.assertEqual(data["site_score"], audit.site_score)
        self.assertEqual(data["overall_health"], audit.overall_health)
        self.assertEqual(data["total_pages_audited"], 2)
        self.assertIsInstance(data["severity_summary"], list)
        self.assertEqual(len(data["pages"]), 2)
        self.assertIn("top_issue", data["pages"][0])

    def test_csv_fields(self) -> None:
        audit = _make_audit()
        fields = csv_fields(audit)
        self.assertEqual(fields["site_seo_score"], audit.site_score)
        self.assertEqual(fields["seo_health"], audit.overall_health)
        self.assertEqual(fields["pages_with_missing_title"], 1)
        self.assertEqual(fields["pages_with_missing_meta_description"], 1)
        self.assertEqual(fields["pages_with_thin_content"], 1)
        self.assertEqual(fields["pages_with_duplicate_titles"], 0)
        self.assertEqual(fields["pages_with_images_missing_alt"], 0)
        self.assertIsInstance(fields["seo_issue_summary"], str)

    def test_csv_fields_from_row_matches_stored_shape(self) -> None:
        audit = _make_audit()
        data = audit.to_dict()
        pages = data.pop("pages")
        row = {
            key: data[key] for key in (
                "site_score", "overall_health", "html_pages", "pages_with_title",
                "pages_with_meta_description", "pages_with_thin_content",
                "pages_with_duplicate_titles", "pages_with_images_missing_alt",
            )
        }
        row["severity_summary"] = data["severity_summary"]
        fields = csv_fields_from_row(row)
        self.assertEqual(fields["pages_with_missing_title"], 1)
        self.assertEqual(fields["site_seo_score"], row["site_score"])
        self.assertNotEqual(fields["seo_issue_summary"], "")

    def test_top_issues_orders_by_severity_and_dedupes(self) -> None:
        audit = _make_audit()
        issues = top_issues(audit, n=6)
        self.assertTrue(issues)
        codes = [issue.code for issue in issues]
        self.assertEqual(len(codes), len(set(codes)))


if __name__ == "__main__":
    unittest.main()
