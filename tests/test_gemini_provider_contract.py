import json
import unittest
from unittest.mock import patch

from app.services.providers.base_provider import ProviderError, ProviderPrompt
from app.services.providers.gemini_provider import GeminiProvider


class FakeGeminiResponse:
    status = 200

    def __init__(self, text: str = "{}") -> None:
        self.text = text

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self) -> bytes:
        return json.dumps(
            {
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {
                                    "text": self.text,
                                }
                            ]
                        }
                    }
                ]
            }
        ).encode("utf-8")


class GeminiProviderContractTest(unittest.TestCase):
    def provider(self) -> GeminiProvider:
        return GeminiProvider(
            api_key="test-key",
            base_url="https://gemini.test/v1beta",
            default_model="gemini-test",
            models=("gemini-test",),
        )

    def test_gemini_uses_prompt_response_schema_for_recommendation_object(self) -> None:
        captured = {}
        schema = {
            "type": "OBJECT",
            "properties": {
                "recommended_candidate_id": {"type": "STRING", "enum": ["A", "B"]},
                "reason": {"type": "STRING"},
                "warnings": {"type": "ARRAY", "items": {"type": "STRING"}},
            },
            "required": ["recommended_candidate_id", "reason", "warnings"],
        }

        def fake_urlopen(request, timeout):
            captured["payload"] = json.loads(request.data.decode("utf-8"))
            return FakeGeminiResponse(
                json.dumps(
                    {
                        "recommended_candidate_id": "A",
                        "reason": "Best base.",
                        "warnings": [],
                    }
                )
            )

        with patch("app.services.providers.gemini_provider.urlopen", side_effect=fake_urlopen):
            self.provider().generate(
                prompt=ProviderPrompt(
                    system_contract="Return a recommendation object.",
                    task_payload="Choose one.",
                    response_schema=schema,
                ),
                model="gemini-test",
            )

        generation_config = captured["payload"]["generationConfig"]
        self.assertEqual(generation_config["responseSchema"], schema)
        self.assertEqual(generation_config["responseSchema"]["type"], "OBJECT")
        self.assertNotIn("Rubric_dimensions", json.dumps(generation_config["responseSchema"]))

    def test_gemini_uses_prompt_response_schema_for_rubric_array(self) -> None:
        captured = {}
        schema = {
            "type": "ARRAY",
            "minItems": 6,
            "maxItems": 6,
            "items": {
                "type": "OBJECT",
                "properties": {
                    "Rubric_dimensions": {
                        "type": "STRING",
                        "enum": ["Natural Language Fluency"],
                    },
                    "Rubric_title": {"type": "STRING"},
                    "Rubrics_description": {"type": "STRING"},
                    "Rubrics_weight": {"type": "INTEGER", "minimum": -7, "maximum": 10},
                    "is_response_specific": {"type": "BOOLEAN"},
                },
                "required": [
                    "Rubric_dimensions",
                    "Rubric_title",
                    "Rubrics_description",
                    "Rubrics_weight",
                    "is_response_specific",
                ],
            },
        }

        def fake_urlopen(request, timeout):
            captured["payload"] = json.loads(request.data.decode("utf-8"))
            return FakeGeminiResponse("[]")

        with patch("app.services.providers.gemini_provider.urlopen", side_effect=fake_urlopen):
            self.provider().generate(
                prompt=ProviderPrompt(
                    system_contract="Return rubric JSON.",
                    task_payload="Generate rubrics.",
                    response_schema=schema,
                ),
                model="gemini-test",
            )

        generation_config = captured["payload"]["generationConfig"]
        self.assertEqual(generation_config["responseSchema"], schema)
        self.assertEqual(generation_config["responseSchema"]["minItems"], 6)
        self.assertEqual(generation_config["responseSchema"]["maxItems"], 6)

    def test_gemini_timeout_becomes_provider_error(self) -> None:
        with patch("app.services.providers.gemini_provider.urlopen", side_effect=TimeoutError("timed out")):
            with self.assertRaisesRegex(ProviderError, "Gemini timed out after 180 seconds"):
                self.provider().generate(
                    prompt=ProviderPrompt(
                        system_contract="Return JSON.",
                        task_payload="Generate.",
                    ),
                    model="gemini-test",
                )


if __name__ == "__main__":
    unittest.main()
