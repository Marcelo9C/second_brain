import json
import unittest
from unittest.mock import patch

from app.services.providers.base_provider import BaseProvider, ProviderError, ProviderPrompt, ProviderResult
from app.services.providers.ollama_provider import OllamaProvider
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

    def __init__(
        self,
        *,
        fail: bool = False,
        force_model_used: str | None = None,
        force_provider_used: str | None = None,
        response_text: str | None = None,
        name: str = "fake",
        models: list[str] | None = None,
        default_model_name: str = "fake-default",
    ) -> None:
        self.name = name
        self.label = f"{name} Provider"
        self.fail = fail
        self.calls = 0
        self.force_model_used = force_model_used
        self.force_provider_used = force_provider_used
        self.response_text = response_text
        self.models = models or ["fake-model", "fake-default"]
        self.default_model_name = default_model_name

    def list_models(self) -> list[dict]:
        return [{"name": model} for model in self.models]

    def default_model(self) -> str:
        return self.default_model_name

    def generate(self, *, prompt: ProviderPrompt | str, model: str | None = None) -> ProviderResult:
        self.calls += 1
        if self.fail:
            raise ProviderError("Synthetic provider failure.")
        
        used_model = self.force_model_used or model or self.default_model()
        used_provider = self.force_provider_used or self.name
        return ProviderResult(
            text=self.response_text if self.response_text is not None else json.dumps(generated_rubrics()),
            provider_used=used_provider,
            model_used=used_model,
            exact_url_called="http://fake.local/generate",
            response_status=200,
            duration_ms=1,
        )


class RubricGenerationServiceTest(unittest.TestCase):
    def service(self, provider: FakeProvider) -> RubricGenerationService:
        return RubricGenerationService(providers={"fake": provider}, default_provider="fake")

    def multi_provider_service(self, *providers: FakeProvider) -> RubricGenerationService:
        return RubricGenerationService(
            providers={provider.name: provider for provider in providers},
            default_provider=providers[0].name,
        )

    def test_empty_draft_does_not_call_provider(self) -> None:
        provider = FakeProvider()

        result = self.service(provider).generate({})

        self.assertEqual(provider.calls, 0)
        self.assertFalse(result["metadata"]["generation_executed"])
        self.assertEqual(result["metadata"]["generation_failure_type"], "none")
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
        self.assertEqual(result["metadata"]["generation_failure_type"], "none")
        self.assertEqual(result["workflow_decision"]["decision"], "generation_succeeded")

    def test_requested_ollama_provider_and_model_are_called(self) -> None:
        ollama = FakeProvider(name="ollama", models=["phi3:mini"], default_model_name="phi3:mini")
        gemini = FakeProvider(name="gemini", models=["gemini-2.5-flash"], default_model_name="gemini-2.5-flash")
        service = self.multi_provider_service(gemini, ollama)

        result = service.generate(ready_payload(provider="ollama", model="phi3:mini"))

        self.assertTrue(result["success"])
        self.assertEqual(ollama.calls, 1)
        self.assertEqual(gemini.calls, 0)
        self.assertEqual(result["metadata"]["provider_requested"], "ollama")
        self.assertEqual(result["metadata"]["model_requested"], "phi3:mini")
        self.assertEqual(result["metadata"]["provider_used"], "ollama")
        self.assertEqual(result["metadata"]["model_used"], "phi3:mini")
        self.assertEqual(result["metadata"]["model_to_call"], "phi3:mini")
        self.assertFalse(result["metadata"]["default_model_used"])

    def test_requested_gemini_provider_and_model_are_called(self) -> None:
        ollama = FakeProvider(name="ollama", models=["phi3:mini"], default_model_name="phi3:mini")
        gemini = FakeProvider(name="gemini", models=["gemini-2.5-flash"], default_model_name="gemini-2.5-flash")
        service = self.multi_provider_service(ollama, gemini)

        result = service.generate(ready_payload(provider="gemini", model="gemini-2.5-flash"))

        self.assertTrue(result["success"])
        self.assertEqual(ollama.calls, 0)
        self.assertEqual(gemini.calls, 1)
        self.assertEqual(result["metadata"]["provider_requested"], "gemini")
        self.assertEqual(result["metadata"]["model_requested"], "gemini-2.5-flash")
        self.assertEqual(result["metadata"]["provider_used"], "gemini")
        self.assertEqual(result["metadata"]["model_used"], "gemini-2.5-flash")

    def test_model_from_previous_provider_is_blocked_before_call(self) -> None:
        ollama = FakeProvider(name="ollama", models=["phi3:mini"], default_model_name="phi3:mini")
        gemini = FakeProvider(name="gemini", models=["gemini-2.5-flash"], default_model_name="gemini-2.5-flash")
        service = self.multi_provider_service(gemini, ollama)

        result = service.generate(ready_payload(provider="ollama", model="gemini-2.5-flash"))

        self.assertFalse(result["success"])
        self.assertEqual(ollama.calls, 0)
        self.assertEqual(gemini.calls, 0)
        self.assertEqual(result["metadata"]["provider_requested"], "ollama")
        self.assertEqual(result["metadata"]["model_requested"], "gemini-2.5-flash")
        self.assertEqual(result["metadata"]["model_to_call"], "gemini-2.5-flash")
        self.assertFalse(result["metadata"]["model_allowed_by_backend"])
        self.assertFalse(result["metadata"]["generation_executed"])
        self.assertEqual(result["metadata"]["blocked_reason"], "model_not_allowed_by_backend")

    def test_generation_prompt_is_generic_and_uses_official_weight_scale(self) -> None:
        prompt = self.service(FakeProvider())._build_prompt(ready_payload()).as_text()

        for forbidden in ("Duda", "Maria", "Valorant", "pôr do sol", "por do sol"):
            self.assertNotIn(forbidden, prompt)
        self.assertNotIn("Few-shot", prompt)
        self.assertNotIn("Task Fulfillment", prompt)
        self.assertNotIn("Safety and Quality", prompt)
        self.assertNotIn("-10", prompt)
        self.assertIn("Rubrics_weight values must be from -5 to 10, except 0.", prompt)
        self.assertIn("-5 to -1", prompt)
        self.assertIn("1 to 10", prompt)
        self.assertIn("Never use 0", prompt)
        self.assertIn("Invalid weights cause the entire generation to be rejected", prompt)
        self.assertIn("atomic", prompt)
        self.assertIn("non-overlapping", prompt)
        self.assertIn("Reflect meaningful differences between response_raw and the Golden Response excerpt", prompt)
        self.assertIn("Do not infer repeated behavior", prompt)

    def test_generated_rubric_validation_uses_official_weight_scale(self) -> None:
        service = self.service(FakeProvider())
        valid_negative = generated_rubrics()
        valid_negative[0]["Rubrics_weight"] = -1

        report = service._validate_generated_rubrics(valid_negative)

        self.assertEqual(report["status"], "valid")

    def test_generated_rubric_validation_rejects_weight_outside_official_scale(self) -> None:
        service = self.service(FakeProvider())
        invalid_negative = generated_rubrics()
        invalid_negative[0]["Rubrics_weight"] = -6

        with self.assertRaisesRegex(Exception, "between -5 and -1"):
            service._validate_generated_rubrics(invalid_negative)

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
        self.assertEqual(result["metadata"]["generation_failure_type"], "provider_failed")
        self.assertIsNone(result["metadata"]["provider_used"])
        self.assertIsNone(result["metadata"]["model_used"])

    def test_ollama_timeout_becomes_provider_error(self) -> None:
        provider = OllamaProvider(
            base_url="http://localhost:11434",
            fallback_model="phi3:mini",
            generation_timeout_seconds=1,
        )

        with patch("app.services.providers.ollama_provider.urlopen", side_effect=TimeoutError("timed out")):
            with self.assertRaisesRegex(ProviderError, "Ollama timed out after 1 seconds"):
                provider.generate(prompt="Synthetic prompt.", model="phi3:mini")

    def test_http_200_invalid_rubrics_are_not_provider_failure(self) -> None:
        provider = FakeProvider(response_text="[]")

        result = self.service(provider).generate(ready_payload())

        self.assertEqual(provider.calls, 1)
        self.assertFalse(result["success"])
        self.assertIsNone(result["rubrics"])
        self.assertEqual(result["raw_model_response"], "[]")
        self.assertEqual(result["metadata"]["response_status"], 200)
        self.assertEqual(result["metadata"]["validation_status"], "failed")
        self.assertIn("non-empty JSON array", result["metadata"]["validation_error"])
        self.assertEqual(result["metadata"]["generation_failure_type"], "invalid_rubric_response")
        self.assertTrue(result["metadata"]["result_discarded"])
        self.assertNotIn("raw_error", result["metadata"])

    def test_model_call_false_response_does_not_change_rubrics(self) -> None:
        provider = FakeProvider()

        result = self.service(provider).generate(ready_payload(prompt=""))

        self.assertEqual(provider.calls, 0)
        self.assertFalse(result["success"])
        self.assertIsNone(result["rubrics"])
        self.assertFalse(result["workflow_decision"]["model_call"])

    def test_unauthorized_model_is_blocked_preflight(self) -> None:
        provider = FakeProvider()

        result = self.service(provider).generate(ready_payload(model="fake-hacker-model"))

        self.assertEqual(provider.calls, 0)
        self.assertFalse(result["success"])
        self.assertFalse(result["metadata"]["model_allowed_by_backend"])
        self.assertEqual(result["workflow_decision"]["decision"], "blocked")
        self.assertEqual(result["metadata"]["blocked_reason"], "model_not_allowed_by_backend")

    def test_default_model_is_used_when_none_requested(self) -> None:
        provider = FakeProvider()

        payload = ready_payload()
        del payload["model"]  # Remove model requested
        
        result = self.service(provider).generate(payload)

        self.assertEqual(provider.calls, 1)
        self.assertTrue(result["success"])
        self.assertEqual(result["metadata"]["model_to_call"], "fake-default")
        self.assertTrue(result["metadata"]["default_model_used"])
        self.assertEqual(result["metadata"]["model_used"], "fake-default")

    def test_fallback_is_discarded_post_call(self) -> None:
        provider = FakeProvider(force_model_used="fake-cheap-model")

        result = self.service(provider).generate(ready_payload(model="fake-model"))

        self.assertEqual(provider.calls, 1)
        self.assertFalse(result["success"])
        self.assertTrue(result["metadata"]["fallback_applied"])
        self.assertTrue(result["metadata"]["result_discarded"])
        self.assertEqual(result["metadata"]["generation_failure_type"], "provider_mismatch_discarded")
        self.assertEqual(result["metadata"]["blocked_reason"], "provider_executed_different_model")

    def test_provider_mismatch_is_discarded_post_call(self) -> None:
        provider = FakeProvider(force_provider_used="different-provider")

        result = self.service(provider).generate(ready_payload(model="fake-model"))

        self.assertEqual(provider.calls, 1)
        self.assertFalse(result["success"])
        self.assertTrue(result["metadata"]["fallback_applied"])
        self.assertTrue(result["metadata"]["result_discarded"])
        self.assertEqual(result["metadata"]["generation_failure_type"], "provider_mismatch_discarded")
        self.assertEqual(result["metadata"]["blocked_reason"], "provider_executed_different_provider")

    def test_no_default_model_configured_blocks_call(self) -> None:
        class NoDefaultModelProvider(BaseProvider):
            name = "no-default"
            label = "No Default"
            implemented = True
            
            def __init__(self):
                self.calls = 0
                
            def list_models(self) -> list[dict]:
                return [{"name": "some-model"}]
                
            def generate(self, *, prompt: ProviderPrompt | str, model: str | None = None) -> ProviderResult:
                self.calls += 1
                return ProviderResult(
                    text="[]",
                    provider_used=self.name,
                    model_used=model or "none",
                    exact_url_called="http://fake",
                    response_status=200,
                    duration_ms=1,
                )
                
        provider = NoDefaultModelProvider()
        
        payload = ready_payload()
        del payload["model"]  # Remove model requested to trigger default fallback
        
        result = self.service(provider).generate(payload)

        self.assertEqual(provider.calls, 0)
        self.assertFalse(result["success"])
        self.assertIsNone(result["rubrics"])
        self.assertFalse(result["metadata"]["default_model_configured"])
        self.assertFalse(result["metadata"]["model_allowed_by_backend"])
        self.assertEqual(result["metadata"]["blocked_reason"], "default_model_not_configured")
        self.assertEqual(result["workflow_decision"]["decision"], "blocked")


if __name__ == "__main__":
    unittest.main()
