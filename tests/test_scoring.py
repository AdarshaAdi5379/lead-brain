import unittest

from src.scoring import score_lead


class TestScoring(unittest.TestCase):
    def test_no_website_ignores_other_rules(self) -> None:
        result = score_lead(
            {
                "website_url": "",
                "phone": "",
                "email": "",
                "platform": "wix",
                "load_speed": "slow",
                "complexity": "complex",
            }
        )
        self.assertEqual(result.score, 90)  # 50 + 40 only
        self.assertEqual(result.priority, "Hot")

    def test_basic_wix_slow_missing_contacts(self) -> None:
        result = score_lead(
            {
                "website_url": "https://example.com",
                "platform": "Wix",
                "load_speed": "slow",
                "phone": "",
                "email": "",
            }
        )
        # 50 + 30 + 20 + 15 + 15 = 130 -> clamp 100
        self.assertEqual(result.score, 100)
        self.assertEqual(result.priority, "Hot")
        self.assertTrue(result.reasons)

    def test_wordpress_basic_bonus(self) -> None:
        result = score_lead(
            {
                "website_url": "https://example.com",
                "platform": "WordPress",
                "complexity": "basic",
                "phone": "123",
                "email": "a@b.com",
            }
        )
        # baseline 50 +10 -10 -10 = 40 => Cold
        self.assertEqual(result.score, 40)
        self.assertEqual(result.priority, "Cold")


if __name__ == "__main__":
    unittest.main()

