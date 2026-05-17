import unittest

from src.extraction_schema import validate_extracted_lead


class TestExtractionSchema(unittest.TestCase):
    def test_requires_url_key(self) -> None:
        with self.assertRaises(ValueError):
            validate_extracted_lead({"business_name": "Acme"})

    def test_normalizes_enums_and_nulls(self) -> None:
        lead = validate_extracted_lead(
            {
                "url": " https://example.com ",
                "business_name": "  ",
                "phone": None,
                "email": "a@b.com",
                "platform": "WordPress",
                "complexity": "BASIC",
                "load_speed": "slow",
                "extraction_success": "true",
            }
        )
        self.assertEqual(lead.url, "https://example.com")
        self.assertIsNone(lead.business_name)
        self.assertEqual(lead.platform, "wordpress")
        self.assertEqual(lead.complexity, "basic")
        self.assertEqual(lead.load_speed, "slow")
        self.assertTrue(lead.extraction_success)


if __name__ == "__main__":
    unittest.main()

