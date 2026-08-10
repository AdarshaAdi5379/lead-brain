import io
import json
import os
import unittest
import urllib.error
from unittest.mock import patch

from src.contact.sources import CSV, LLM, VISIBLE_TEXT, pick_across_sources
from src.llm.openai_responses import OpenAIHTTPError, _api_key, _base_url, create_response
from src.llm_extraction import _resolve_extraction_models, extract_lead_from_fetch
from src.scraping.browser_fetch import FetchResult
from src.url_loader import SeedRow

import main as main_module

CHAT_URL = "https://openrouter.ai/api/v1/chat/completions"


class _FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._raw = json.dumps(payload).encode("utf-8")

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *args) -> bool:
        return False

    def read(self) -> bytes:
        return self._raw


def _http_error(status: int, body: str = "boom") -> urllib.error.HTTPError:
    return urllib.error.HTTPError(
        CHAT_URL, status, "err", {}, io.BytesIO(body.encode("utf-8"))
    )


def _fetch() -> FetchResult:
    return FetchResult(
        url="https://example.com",
        final_url="https://example.com",
        success=True,
        status=200,
        html="<html><body><h1>Acme Plumbing</h1></body></html>",
        text="Acme Plumbing, Austin TX",
        error=None,
    )


def _seed() -> SeedRow:
    return SeedRow(
        business_name="Acme Plumbing",
        category="plumber",
        url="https://example.com",
        city="Austin",
        state="TX",
    )


def _valid_extraction_payload() -> dict:
    return {
        "choices": [
            {
                "message": {
                    "content": json.dumps(
                        {
                            "url": "https://example.com",
                            "business_name": "Acme Plumbing",
                            "phone": "512-555-0100",
                            "email": "hello@example.com",
                            "platform": "unknown",
                            "complexity": "unknown",
                            "load_speed": "unknown",
                            "extraction_success": True,
                            "last_error": None,
                        }
                    )
                }
            }
        ],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    }


class TestOpenRouterConfig(unittest.TestCase):
    def test_default_base_url(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(_base_url(), "https://openrouter.ai/api/v1")

    def test_base_url_from_env(self) -> None:
        with patch.dict(
            os.environ, {"OPENROUTER_BASE_URL": "https://custom.example/v2"}, clear=True
        ):
            self.assertEqual(_base_url(), "https://custom.example/v2")

    def test_default_model_resolution(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(
                _resolve_extraction_models(None, None), ("openrouter/free", "openrouter/free")
            )

    def test_model_override_env(self) -> None:
        with patch.dict(
            os.environ, {"OPENROUTER_MODEL": "deepseek/deepseek-chat"}, clear=True
        ):
            primary, _fallback = _resolve_extraction_models(None, None)
            self.assertEqual(primary, "deepseek/deepseek-chat")

    def test_model_override_parameter_wins(self) -> None:
        with patch.dict(os.environ, {"OPENROUTER_MODEL": "env-model"}, clear=True):
            primary, _fallback = _resolve_extraction_models("param-model", None)
            self.assertEqual(primary, "param-model")

    def test_legacy_openai_model_honored(self) -> None:
        with patch.dict(
            os.environ, {"OPENAI_MODEL_PRIMARY": "gpt-4.1-nano"}, clear=True
        ):
            primary, _fallback = _resolve_extraction_models(None, None)
            self.assertEqual(primary, "gpt-4.1-nano")

    def test_api_key_loaded_from_env(self) -> None:
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "sk-test-key"}, clear=True):
            self.assertEqual(_api_key(), "sk-test-key")

    def test_api_key_missing_raises_without_leaking(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(RuntimeError) as ctx:
                _api_key()
            message = str(ctx.exception)
            self.assertIn("OPENROUTER_API_KEY", message)
            self.assertNotIn("sk-", message)


class TestOpenRouterResponse(unittest.TestCase):
    def test_successful_response_parsed(self) -> None:
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "sk-test"}, clear=True):
            with patch("urllib.request.urlopen", return_value=_FakeResponse(_valid_extraction_payload())) as mock_urlopen:
                output_text, usage, payload = create_response(
                    model="openrouter/free",
                    system_prompt="sys",
                    user_prompt="user",
                )
        self.assertIn("Acme Plumbing", output_text)
        self.assertIsNotNone(usage)
        self.assertEqual(usage.input_tokens, 10)
        self.assertEqual(usage.output_tokens, 5)
        self.assertEqual(usage.total_tokens, 15)
        request = mock_urlopen.call_args[0][0]
        self.assertTrue(request.full_url.endswith("/chat/completions"))
        self.assertEqual(request.headers["Authorization"], "Bearer sk-test")
        body = json.loads(request.data.decode("utf-8"))
        self.assertEqual(body["model"], "openrouter/free")

    def test_successful_extraction_validates_schema(self) -> None:
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "sk-test"}, clear=True):
            with patch("urllib.request.urlopen", return_value=_FakeResponse(_valid_extraction_payload())):
                result = extract_lead_from_fetch(_fetch())
        self.assertTrue(result.lead.extraction_success)
        self.assertEqual(result.lead.business_name, "Acme Plumbing")
        self.assertEqual(result.lead.phone, "512-555-0100")
        self.assertIsNotNone(result.usage)

    def test_malformed_json_yields_pipeline_safe_failed_lead(self) -> None:
        payload = {"choices": [{"message": {"content": "sorry, no json here"}}]}
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "sk-test"}, clear=True):
            with patch("urllib.request.urlopen", return_value=_FakeResponse(payload)):
                result = main_module._extract_from_fetch(_seed(), _fetch())
        self.assertFalse(result["extraction_success"])
        self.assertIn("LLM extraction failed", result["last_error"] or "")
        self.assertEqual(result["business_name"], "Acme Plumbing")


class TestOpenRouterFailureHandling(unittest.TestCase):
    def _call(self, *, urlopen_side_effect):
        from src.llm_extraction import _call_llm

        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "sk-test"}, clear=True):
            with patch("urllib.request.urlopen", side_effect=urlopen_side_effect) as mock_urlopen:
                try:
                    _call_llm(
                        model="openrouter/free",
                        system_prompt="s",
                        user_prompt="u",
                        fallback="openrouter/free",
                        timeout_s=60,
                    )
                except Exception:
                    pass
        return mock_urlopen

    def test_429_not_retried(self) -> None:
        mock_urlopen = self._call(urlopen_side_effect=_http_error(429, "rate limited"))
        self.assertEqual(mock_urlopen.call_count, 1)

    def test_401_invalid_key_not_retried(self) -> None:
        mock_urlopen = self._call(urlopen_side_effect=_http_error(401, "invalid key"))
        self.assertEqual(mock_urlopen.call_count, 1)

    def test_403_not_retried(self) -> None:
        mock_urlopen = self._call(urlopen_side_effect=_http_error(403, "forbidden"))
        self.assertEqual(mock_urlopen.call_count, 1)

    def test_500_retried_once_then_raises(self) -> None:
        from src.llm_extraction import _call_llm

        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "sk-test"}, clear=True):
            with patch(
                "urllib.request.urlopen",
                side_effect=[_http_error(500, "server error"), _http_error(500, "server error")],
            ) as mock_urlopen:
                with self.assertRaises(OpenAIHTTPError):
                    _call_llm(
                        model="openrouter/free",
                        system_prompt="s",
                        user_prompt="u",
                        fallback="openrouter/free",
                        timeout_s=60,
                    )
        self.assertEqual(mock_urlopen.call_count, 2)

    def test_500_retried_with_fallback_model_then_succeeds(self) -> None:
        with patch.dict(
            os.environ,
            {
                "OPENROUTER_API_KEY": "sk-test",
                "OPENROUTER_MODEL": "some-primary",
                "OPENAI_MODEL_FALLBACK": "some-fallback",
            },
            clear=True,
        ):
            from src.llm_extraction import _call_llm

            with patch(
                "urllib.request.urlopen",
                side_effect=[_http_error(500, "server error"), _FakeResponse(_valid_extraction_payload())],
            ) as mock_urlopen:
                output_text, usage = _call_llm(
                    model="some-primary",
                    system_prompt="s",
                    user_prompt="u",
                    fallback="some-fallback",
                    timeout_s=60,
                )
        self.assertEqual(mock_urlopen.call_count, 2)
        self.assertIn("Acme Plumbing", output_text)
        self.assertIsNotNone(usage)
        bodies = [json.loads(call.args[0].data.decode("utf-8")) for call in mock_urlopen.call_args_list]
        self.assertEqual(bodies[0]["model"], "some-primary")
        self.assertEqual(bodies[1]["model"], "some-fallback")

    def test_timeout_retried_once_then_succeeds(self) -> None:
        from src.llm_extraction import _call_llm

        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "sk-test"}, clear=True):
            with patch(
                "urllib.request.urlopen",
                side_effect=[
                    urllib.error.URLError("timed out"),
                    _FakeResponse(_valid_extraction_payload()),
                ],
            ) as mock_urlopen:
                output_text, usage = _call_llm(
                    model="openrouter/free",
                    system_prompt="s",
                    user_prompt="u",
                    fallback="openrouter/free",
                    timeout_s=60,
                )
        self.assertEqual(mock_urlopen.call_count, 2)
        self.assertIn("Acme Plumbing", output_text)
        self.assertIsNotNone(usage)

    def test_429_through_pipeline_degrades_to_failed_lead(self) -> None:
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "sk-test"}, clear=True):
            with patch(
                "src.llm.openai_responses.create_response",
                side_effect=OpenAIHTTPError(429, "rate limited"),
            ):
                payload = main_module._extract_from_fetch(_seed(), _fetch())
        self.assertFalse(payload["extraction_success"])
        self.assertIn("LLM extraction failed", payload["last_error"] or "")

    def test_deterministic_contact_survives_llm_failure(self) -> None:
        deterministic_phone = ("512-555-0100", VISIBLE_TEXT, None)
        failed_llm = (None, LLM, None)
        seed_csv = (None, CSV, None)
        phone, source, _confidence = pick_across_sources(
            deterministic_phone, failed_llm, seed_csv
        )
        self.assertEqual(phone, "512-555-0100")
        self.assertEqual(source, VISIBLE_TEXT)

    def test_deterministic_contact_beats_llm_when_both_present(self) -> None:
        deterministic_phone = ("512-555-0100", VISIBLE_TEXT, None)
        llm_phone = ("000-000-0000", LLM, 0.9)
        phone, source, _confidence = pick_across_sources(deterministic_phone, llm_phone)
        self.assertEqual(phone, "512-555-0100")
        self.assertEqual(source, VISIBLE_TEXT)


if __name__ == "__main__":
    unittest.main()