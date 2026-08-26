import tempfile
import unittest
from pathlib import Path

from src.url_loader import load_seed_csv

CSV = "business_name,category,url,city,state\n{name},{category},{url},{city},{state}\n"


def _write(tmp: str, url: str) -> Path:
    path = Path(tmp) / "seeds.csv"
    path.write_text(CSV.format(name="Acme", category="plumber", url=url, city="Austin", state="TX"), encoding="utf-8")
    return path


class TestURLLoaderValidation(unittest.TestCase):
    def test_missing_required_headers_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "seeds.csv"
            path.write_text("name,url\nAcme,example.com\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                load_seed_csv(path)

    def test_accepts_alias_headers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "seeds.csv"
            path.write_text(
                "company,service,homepage,town,region\nAcme,plumber,example.com,Austin,TX\n",
                encoding="utf-8",
            )
            rows = load_seed_csv(path)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0].business_name, "Acme")
            self.assertEqual(rows[0].category, "plumber")
            self.assertEqual(rows[0].city, "Austin")
            self.assertEqual(rows[0].state, "TX")


class TestSeedUrlTrustBoundary(unittest.TestCase):
    """Phase R1: unsafe seed URLs are rejected before any fetch can happen."""

    def test_valid_public_url_survives_unchanged(self) -> None:
        for good in (
            "https://example.com",
            "http://example.com",
            "https://plumbing.example.co.uk/services?ref=1#top",
            "example.com",  # bare domains keep the historic https upgrade
        ):
            with self.subTest(url=good):
                with tempfile.TemporaryDirectory() as tmp:
                    rows = load_seed_csv(_write(tmp, good))
                    self.assertEqual(len(rows), 1)
                    self.assertIsNotNone(rows[0].url)
                    self.assertTrue(rows[0].url.startswith("http"))
                    self.assertIsNone(rows[0].url_error)

    def test_empty_url_stays_plain_no_website(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            rows = load_seed_csv(_write(tmp, ""))
            self.assertEqual(len(rows), 1)
            self.assertIsNone(rows[0].url)
            self.assertIsNone(rows[0].url_error)  # no URL: not an error, just absent

    def test_unsafe_urls_rejected_with_reason(self) -> None:
        unsafe = {
            "file:///etc/passwd": "scheme",
            "ftp://example.com": "scheme",
            "gopher://example.com": "scheme",
            "javascript:alert(1)": "scheme",
            "data:text/plain,test": "scheme",
            "http://127.0.0.1:6379": "private",
            "http://169.254.169.254/": "private",
            "http://10.1.2.3/": "private",
            "http://172.16.5.5/": "private",
            "http://192.168.0.20/": "private",
            "http://localhost/admin": "localhost",
            "https://user:password@example.com": "credentials",
        }
        for bad, hint in unsafe.items():
            with self.subTest(url=bad):
                with tempfile.TemporaryDirectory() as tmp:
                    rows = load_seed_csv(_write(tmp, bad))
                    self.assertEqual(len(rows), 1)
                    row = rows[0]
                    # Never handed to the fetch path...
                    self.assertIsNone(row.url)
                    # ...but not silently turned into a missing website either.
                    self.assertIsNotNone(row.url_error)
                    self.assertIn("Invalid/unsafe website URL", row.url_error or "")
                    if hint == "credentials":
                        self.assertIn("credentials", row.url_error or "")


if __name__ == "__main__":
    unittest.main()

