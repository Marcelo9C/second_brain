import json
import unittest

from app.services.providers.base_provider import BaseProvider, ProviderError, ProviderPrompt, ProviderResult
from app.services.rubric_generation_service import RubricGenerationService


def ready_payload(**overrides):
    payload = {
        "locale": "pt-BR",
        "category": "Writing",
        "prompt": "Synthetic prompt.",
        "response_raw": "Synthetic model response.",
        "golden_response": "Synthetic golden response.",
        "base_template": [{"slot": "synthetic"}],
        "provider": "fake",
        "model": "fake-model",
    }
    payload.update(overrides)
    return payload


def generated_rubrics() -> list[dict]:
    return [
        {
            "Rubric_dimensions": "Natural Language Fluency",
            "Rubric_title": "Clear Expression",
            "Rubrics_description": "The response is written clearly enough for evaluation.",
            "Rubrics_weight": 7,
            "is_response_specific": False,
        }
    ]


class FakeProvider(BaseProvider):
    name = "fake"
    label = "Fake Provider"
    implemented = True

    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls = 0

    def list_models(self) -> list[dict]:
        return [{"name": "fake-model"}]

    def generate(self, *, prompt: ProviderPrompt | str, model: str | None = None) -> ProviderResult:
        self.calls += 1
        if self.fail:
            raise ProviderError("Synthetic provider failure.")
        return ProviderResult(
            text=json.dumps(generated_rubrics()),
            provider_used=self.name,
            model_used=model or "fake-model",
            exact_url_called="http://fake.local/generate",
            response_status=200,
            duration_ms=1,
        )


class RubricGenerationServiceTest(unittest.TestCase):
    def service(self, provider: FakeProvider) -> RubricGenerationService:
        return RubricGenerationService(providers={"fake": provider}, default_provider="fake")

    def test_empty_draft_does_not_call_provider(self) -> None:
        provider = FakeProvider()

        result = self.service(provider).generate({})

        self.assertEqual(provider.calls, 0)
        self.assertFalse(result["metadata"]["generation_executed"])
        self.assertIsNone(result["rubrics"])
        self.assertEqual(result["workflow_decision"]["decision"], "not_ready")

    def test_scaffold_without_real_case_does_not_call_provider(self) -> None:
        provider = FakeProvider()

        result = self.service(provider).generate(
            ready_payload(prompt="", response_raw="", golden_response="")
        )

        self.assertEqual(provider.calls, 0)
        self.assertFalse(result["metadata"]["generation_executed"])
        self.assertIsNone(result["rubrics"])

    def test_rubrics_without_case_data_do_not_call_provider(self) -> None:
        provider = FakeProvider()

        result = self.service(provider).generate(
            {
                "locale": "pt-BR",
                "category": "Writing",
                "rubrics": generated_rubrics(),
                "metadata": {"rubric_source": "editor_draft"},
                "provider": "fake",
                "model": "fake-model",
            }
        )

        self.assertEqual(provider.calls, 0)
        self.assertIsNone(result["rubrics"])
        self.assertIn("prompt", result["workflow_decision"]["missing_fields"])

    def test_ready_case_calls_provider_once(self) -> None:
        provider = FakeProvider()

        result = self.service(provider).generate(ready_payload())

        self.assertEqual(provider.calls, 1)
        self.assertTrue(result["success"])
        self.assertEqual(result["workflow_decision"]["decision"], "generation_succeeded")

    def test_template_scaffold_with_ready_case_calls_provider_once(self) -> None:
        provider = FakeProvider()

        result = self.service(provider).generate(
            ready_payload(metadata={"template_scaffold": {"template_name": "synthetic.json"}})
        )

        self.assertEqual(provider.calls, 1)
        self.assertTrue(result["success"])

    def test_provider_failure_after_model_call_becomes_generation_failed(self) -> None:
        provider = FakeProvider(fail=True)

        result = self.service(provider).generate(ready_payload())

        self.assertEqual(provider.calls, 1)
        self.assertFalse(result["success"])
        self.assertEqual(result["workflow_decision"]["decision"], "generation_failed")
        self.assertEqual(result["metadata"]["raw_error"], "Synthetic provider failure.")

    def test_model_call_false_response_does_not_change_rubrics(self) -> None:
        provider = FakeProvider()

        result = self.service(provider).generate(ready_payload(prompt=""))

        self.assertEqual(provider.calls, 0)
        self.assertFalse(result["success"])
        self.assertIsNone(result["rubrics"])
        self.assertFalse(result["workflow_decision"]["model_call"])


if __name__ == "__main__":
    unittest.main()
