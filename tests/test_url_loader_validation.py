import tempfile
import unittest
from pathlib import Path

from src.url_loader import load_seed_csv


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


if __name__ == "__main__":
    unittest.main()

