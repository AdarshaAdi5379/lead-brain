import unittest

from src.llm_extraction import _parse_json_object, _sanitize_email, _sanitize_phone


class TestLLMExtractionParsing(unittest.TestCase):
    def test_parse_plain_json(self) -> None:
        payload = _parse_json_object('{"url": "https://a.com", "platform": "unknown"}')
        self.assertEqual(payload["url"], "https://a.com")

    def test_parse_code_fenced_json(self) -> None:
        payload = _parse_json_object('```json\n{"url": null, "platform": "unknown"}\n```')
        self.assertIn("platform", payload)

    def test_parse_embedded_json(self) -> None:
        payload = _parse_json_object('Here you go:\n{"url":"x","platform":"unknown"}\nThanks!')
        self.assertEqual(payload["url"], "x")

    def test_sanitize_email(self) -> None:
        self.assertEqual(_sanitize_email("Email: hello@example.com"), "hello@example.com")
        self.assertIsNone(_sanitize_email("not an email"))

    def test_sanitize_phone(self) -> None:
        self.assertEqual(_sanitize_phone("Phone: +1 (555) 123-4567"), "+1 (555) 123-4567")
        self.assertIsNone(_sanitize_phone("call us at five five five"))


if __name__ == "__main__":
    unittest.main()

