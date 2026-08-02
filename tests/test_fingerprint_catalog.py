import json
import re
import tempfile
import unittest
from pathlib import Path

from src.fingerprinting.base import (
    CATEGORY_LABELS,
    FingerprintCatalog,
    FingerprintError,
    Technology,
    load_catalog,
)


class TestFingerprintCatalog(unittest.TestCase):
    def test_default_catalog_loads(self) -> None:
        catalog = load_catalog()
        self.assertGreater(len(catalog), 0)

    def test_catalog_covers_expected_stack(self) -> None:
        catalog = load_catalog()
        names = {technology.name for technology in catalog}
        for expected in (
            "WordPress",
            "Wix",
            "Squarespace",
            "Shopify",
            "Next.js",
            "React",
            "Vue",
            "Bootstrap",
            "Tailwind CSS",
            "jQuery",
            "Django",
            "Laravel",
            "Cloudflare",
            "Google Analytics",
            "Stripe",
            "WooCommerce",
        ):
            self.assertIn(expected, names)

    def test_all_signal_regexes_compile(self) -> None:
        catalog = load_catalog()
        for technology in catalog:
            for signal in technology.signals:
                if signal.pattern:
                    re.compile(signal.pattern, re.IGNORECASE)
                if signal.target:
                    re.compile(signal.target, re.IGNORECASE)

    def test_all_categories_are_labeled(self) -> None:
        catalog = load_catalog()
        for technology in catalog:
            self.assertIn(technology.category, CATEGORY_LABELS)

    def test_load_from_list_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "fp.json"
            path.write_text(
                json.dumps(
                    [
                        {
                            "name": "FooCMS",
                            "category": "cms",
                            "signals": [
                                {"kind": "generator", "weight": 40, "pattern": "FooCMS"}
                            ],
                        }
                    ]
                ),
                encoding="utf-8",
            )
            catalog = load_catalog(path)
            self.assertEqual(len(catalog), 1)
            self.assertEqual(catalog.get("cms", "FooCMS").name, "FooCMS")

    def test_load_from_object_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "fp.json"
            path.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "technologies": [
                            {
                                "name": "BarCMS",
                                "category": "cms",
                                "signals": [],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            catalog = load_catalog(path)
            self.assertEqual(len(catalog), 1)
            self.assertEqual(catalog.get("cms", "BarCMS").name, "BarCMS")

    def test_malformed_entry_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "fp.json"
            path.write_text(
                json.dumps([{"name": "", "category": "cms"}]),
                encoding="utf-8",
            )
            with self.assertRaises(FingerprintError):
                load_catalog(path)

    def test_unknown_signal_kind_rejected(self) -> None:
        with self.assertRaises(FingerprintError):
            Technology(
                name="Bad",
                category="cms",
                signals=[__import__("src.fingerprinting.base", fromlist=["Signal"]).Signal(kind="nonsense")],
            )

    def test_register_from_dict(self) -> None:
        catalog = FingerprintCatalog()
        catalog.register_from_dict(
            {"name": "ACME", "category": "hosting", "signals": []}
        )
        self.assertEqual(len(catalog), 1)
        self.assertEqual(catalog.get("hosting", "ACME").category, "hosting")


if __name__ == "__main__":
    unittest.main()