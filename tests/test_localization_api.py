import json
import unittest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock

from app.main import app
from app.dependencies import get_rubric_generation_service
from app.services.rubric_generation_service import RubricGenerationService
from app.services.providers.base_provider import BaseProvider, ProviderError, ProviderPrompt, ProviderResult


class FakeProviderAPI(BaseProvider):
    name = "fake"
    label = "Fake Provider"
    implemented = True

    def __init__(
        self,
        *,
        fail: bool = False,
        force_model_used: str | None = None,
        force_provider_used: str | None = None,
        name: str = "fake",
        models: list[str] | None = None,
        default_model_name: str = "fake-default",
        response_text: str | None = None,
    ) -> None:
        self.name = name
        self.label = f"{name} Provider"
        self.fail = fail
        self.calls = 0
        self.force_model_used = force_model_used
        self.force_provider_used = force_provider_used
        self.models = models or ["fake-model", "fake-default"]
        self.default_model_name = default_model_name
        self.response_text = response_text

    def list_models(self) -> list[dict]:
        return [{"name": model} for model in self.models]

    def default_model(self) -> str | None:
        return self.default_model_name

    def generate(self, *, prompt: ProviderPrompt | str, model: str | None = None) -> ProviderResult:
        self.calls += 1
        if self.fail:
            raise ProviderError("Synthetic provider failure.")
        
        used_model = self.force_model_used or model or self.default_model()
        used_provider = self.force_provider_used or self.name
        
        rubrics = [
            {
                "Rubric_dimensions": "Natural Language Fluency",
                "Rubric_title": "Test Title",
                "Rubrics_description": "Test Desc",
                "Rubrics_weight": 10,
                "is_response_specific": False,
            }
        ]
        
        return ProviderResult(
            text=self.response_text if self.response_text is not None else json.dumps(rubrics),
            provider_used=used_provider,
            model_used=used_model,
            exact_url_called="http://fake.local/generate",
            response_status=200,
            duration_ms=1,
        )


from unittest.mock import patch

class LocalizationApiTest(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        
        self.fake_provider = FakeProviderAPI()
        self.gen_service = RubricGenerationService(
            providers={"fake": self.fake_provider},
            default_provider="fake",
        )
        
        self.patcher = patch("app.api.routes.localization.get_rubric_generation_service", return_value=self.gen_service)
        self.patcher.start()
        
    def tearDown(self):
        self.patcher.stop()
        
    def _ready_payload(self, **overrides):
        payload = {
            "locale": "pt-BR",
            "category": "Writing",
            "prompt": "Synthetic prompt.",
            "response_raw": "Synthetic model response.",
            "golden_response": "Synthetic golden response.",
            "base_template": [
                {
                    "Rubric_dimensions": "Logic and Formatting",
                    "Rubric_title": "TT",
                    "Rubrics_description": "TD",
                    "Rubrics_weight": 10,
                    "is_response_specific": False,
                }
            ],
            "provider": "fake",
            "model": "fake-model",
        }
        payload.update(overrides)
        return payload

    def test_empty_draft_generates_no_call(self):
        payload = self._ready_payload(response_raw="")
        response = self.client.post("/api/localization/rubrics/generate", json=payload)
        
        if response.status_code != 200: print("empty draft error:", response.json())
        self.assertEqual(response.status_code, 200)
        data = response.json()
        
        self.assertFalse(data["metadata"].get("generation_executed", False))
        self.assertFalse(data["workflow_decision"]["model_call"])
        self.assertIsNone(data.get("rubrics"))
        self.assertIsNone(data.get("raw_model_response"))

    def test_template_scaffold_generates_not_ready(self):
        payload = self._ready_payload(prompt="[{context}] -> [{template}]", response_raw="", golden_response="")
        response = self.client.post("/api/localization/rubrics/generate", json=payload)
        
        if response.status_code != 200: print("template scaffold error:", response.json())
        self.assertEqual(response.status_code, 200)
        data = response.json()
        
        self.assertEqual(data["workflow_decision"]["decision"], "not_ready")
        self.assertFalse(data["workflow_decision"]["model_call"])
        self.assertIsNone(data.get("rubrics"))
        self.assertIsNone(data.get("raw_model_response"))

    def test_unauthorized_model_blocks_before_call(self):
        payload = self._ready_payload(model="hacker-model")
        response = self.client.post("/api/localization/rubrics/generate", json=payload)
        
        if response.status_code != 200: print("unauthorized model error:", response.json())
        self.assertEqual(response.status_code, 200)
        data = response.json()
        
        self.assertEqual(data["workflow_decision"]["decision"], "blocked")
        self.assertEqual(data["metadata"]["blocked_reason"], "model_not_allowed_by_backend")
        self.assertFalse(data["metadata"]["model_allowed_by_backend"])
        self.assertEqual(self.fake_provider.calls, 0)
        
    def test_provider_mismatch_discards_result(self):
        # Force the fake provider to return a different model
        self.fake_provider.force_model_used = "sneaky-fallback-model"
        
        payload = self._ready_payload(model="fake-model")
        response = self.client.post("/api/localization/rubrics/generate", json=payload)
        
        if response.status_code != 200: print("provider mismatch error:", response.json())
        self.assertEqual(response.status_code, 200)
        data = response.json()
        
        self.assertEqual(data["workflow_decision"]["decision"], "blocked")
        self.assertTrue(data["metadata"]["fallback_applied"])
        self.assertTrue(data["metadata"]["result_discarded"])
        self.assertEqual(data["metadata"]["generation_failure_type"], "provider_mismatch_discarded")
        self.assertEqual(data["metadata"]["blocked_reason"], "provider_executed_different_model")
        self.assertIsNone(data.get("rubrics"))
        self.assertIsNone(data.get("raw_model_response"))

    def test_provider_failure_returns_explicit_failure_type(self):
        self.fake_provider.fail = True

        response = self.client.post(
            "/api/localization/rubrics/generate",
            json=self._ready_payload(model="fake-model"),
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertFalse(data["success"])
        self.assertEqual(data["metadata"]["generation_failure_type"], "provider_failed")
        self.assertEqual(data["metadata"]["provider_requested"], "fake")
        self.assertEqual(data["metadata"]["model_requested"], "fake-model")
        self.assertEqual(data["metadata"]["raw_error"], "Synthetic provider failure.")
        self.assertIsNone(data["metadata"]["provider_used"])
        self.assertIsNone(data["metadata"]["model_used"])

    def test_empty_rubric_response_returns_invalid_rubric_response(self):
        self.fake_provider.response_text = "[]"

        response = self.client.post(
            "/api/localization/rubrics/generate",
            json=self._ready_payload(model="fake-model"),
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertFalse(data["success"])
        self.assertEqual(data["metadata"]["generation_failure_type"], "invalid_rubric_response")
        self.assertEqual(data["metadata"]["validation_status"], "failed")
        self.assertIn("non-empty JSON array", data["metadata"]["validation_error"])
        self.assertEqual(data["metadata"]["provider_requested"], "fake")
        self.assertEqual(data["metadata"]["model_requested"], "fake-model")

    def test_invalid_dimension_fails_validation(self):
        self.fake_provider.force_model_used = "fake-model"
        
        original_generate = self.fake_provider.generate
        def fake_generate_invalid(*args, **kwargs):
            rubrics = [
                {
                    "Rubric_dimensions": "Invalid Dimension",
                    "Rubric_title": "Test Title",
                    "Rubrics_description": "Test Desc",
                    "Rubrics_weight": 10,
                    "is_response_specific": False,
                }
            ]
            from app.services.providers.base_provider import ProviderResult
            return ProviderResult(
                text=json.dumps(rubrics),
                provider_used="fake",
                model_used="fake-model",
                exact_url_called="http://fake.local/generate",
                response_status=200,
                duration_ms=1,
            )
        self.fake_provider.generate = fake_generate_invalid
        
        try:
            payload = self._ready_payload(model="fake-model")
            response = self.client.post("/api/localization/rubrics/generate", json=payload)
            
            self.assertEqual(response.status_code, 200)
            data = response.json()
            
            self.assertFalse(data["success"])
            self.assertEqual(data["metadata"]["validation_status"], "failed")
            self.assertIn("invalid Rubric_dimensions", data["error"])
        finally:
            self.fake_provider.generate = original_generate

    def test_happy_path_audits_provider_and_model(self):
        payload = self._ready_payload(model="fake-model")
        response = self.client.post("/api/localization/rubrics/generate", json=payload)
        
        if response.status_code != 200: print("happy path error:", response.json())
        self.assertEqual(response.status_code, 200)
        data = response.json()
        
        self.assertTrue(data["success"])
        self.assertTrue(data["metadata"]["generation_executed"])
        self.assertFalse(data["metadata"]["fallback_applied"])
        self.assertEqual(data["metadata"]["provider_used"], "fake")
        self.assertEqual(data["metadata"]["model_used"], "fake-model")
        self.assertIsNotNone(data.get("rubrics"))

    def test_api_routes_requested_ollama_provider_and_model(self):
        ollama_provider = FakeProviderAPI(
            name="ollama",
            models=["phi3:mini"],
            default_model_name="phi3:mini",
        )
        gemini_provider = FakeProviderAPI(
            name="gemini",
            models=["gemini-2.5-flash"],
            default_model_name="gemini-2.5-flash",
        )
        service = RubricGenerationService(
            providers={"ollama": ollama_provider, "gemini": gemini_provider},
            default_provider="gemini",
        )

        with patch("app.api.routes.localization.get_rubric_generation_service", return_value=service):
            response = self.client.post(
                "/api/localization/rubrics/generate",
                json=self._ready_payload(provider="ollama", model="phi3:mini"),
            )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertEqual(ollama_provider.calls, 1)
        self.assertEqual(gemini_provider.calls, 0)
        self.assertEqual(data["metadata"]["provider_requested"], "ollama")
        self.assertEqual(data["metadata"]["model_requested"], "phi3:mini")
        self.assertEqual(data["metadata"]["provider_used"], "ollama")
        self.assertEqual(data["metadata"]["model_used"], "phi3:mini")

    def test_api_blocks_model_from_previous_provider_before_call(self):
        ollama_provider = FakeProviderAPI(
            name="ollama",
            models=["phi3:mini"],
            default_model_name="phi3:mini",
        )
        gemini_provider = FakeProviderAPI(
            name="gemini",
            models=["gemini-2.5-flash"],
            default_model_name="gemini-2.5-flash",
        )
        service = RubricGenerationService(
            providers={"ollama": ollama_provider, "gemini": gemini_provider},
            default_provider="gemini",
        )

        with patch("app.api.routes.localization.get_rubric_generation_service", return_value=service):
            response = self.client.post(
                "/api/localization/rubrics/generate",
                json=self._ready_payload(provider="ollama", model="gemini-2.5-flash"),
            )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertFalse(data["success"])
        self.assertEqual(ollama_provider.calls, 0)
        self.assertEqual(gemini_provider.calls, 0)
        self.assertEqual(data["metadata"]["provider_requested"], "ollama")
        self.assertEqual(data["metadata"]["model_requested"], "gemini-2.5-flash")
        self.assertFalse(data["metadata"]["model_allowed_by_backend"])
        self.assertFalse(data["metadata"]["generation_executed"])
        self.assertEqual(data["metadata"]["blocked_reason"], "model_not_allowed_by_backend")

    def test_valid_rubrics_with_quality_warnings_are_diagnostic(self):
        rubrics = [
            {
                "Rubric_dimensions": "Natural Language Fluency",
                "Rubric_title": f"High Level Criterion {index}",
                "Rubrics_description": "Assesses broad quality in a technically valid synthetic rubric.",
                "Rubrics_weight": 9 if index < 4 else 8,
                "is_response_specific": False,
            }
            for index in range(4)
        ]

        response = self.client.post(
            "/api/localization/rubrics/validate",
            json={
                "locale": "pt-BR",
                "category": "Writing",
                "prompt": "Synthetic writing request.",
                "response_raw": "Synthetic draft answer.",
                "golden_response": "Synthetic revised answer.",
                "rubrics": rubrics,
                "metadata": {},
            },
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["structureValidation"]["status"], "pass")
        self.assertEqual(data["formatValidation"]["status"], "pass")
        self.assertEqual(data["qualityHeuristics"]["status"], "warning")

    def test_valid_rubrics_without_quality_warnings_are_ready_for_human_review(self):
        rubrics = [
            {
                "Rubric_dimensions": "Natural Language Fluency",
                "Rubric_title": "Clear Expression",
                "Rubrics_description": "Assesses whether the answer is clear, readable, and easy to evaluate.",
                "Rubrics_weight": 7,
                "is_response_specific": False,
            },
            {
                "Rubric_dimensions": "Logic and Formatting",
                "Rubric_title": "Structure Fit",
                "Rubrics_description": "Assesses whether the answer follows the expected structure for the task.",
                "Rubrics_weight": 6,
                "is_response_specific": False,
            },
            {
                "Rubric_dimensions": "Cultural Understanding and Application",
                "Rubric_title": "Audience Fit",
                "Rubrics_description": "Assesses whether the answer fits the intended audience and context.",
                "Rubrics_weight": 5,
                "is_response_specific": False,
            },
            {
                "Rubric_dimensions": "Local Facts and Awareness",
                "Rubric_title": "Grounded Claim Handling",
                "Rubrics_description": "Assesses whether factual claims stay grounded and avoid unsupported detail.",
                "Rubrics_weight": 4,
                "is_response_specific": False,
            },
            {
                "Rubric_dimensions": "Logic and Formatting",
                "Rubric_title": "Unsupported Addition Penalty",
                "Rubrics_description": "Penalizes unsupported additions that would reduce evaluation reliability.",
                "Rubrics_weight": -3,
                "is_response_specific": False,
            },
        ]

        response = self.client.post(
            "/api/localization/rubrics/validate",
            json={
                "locale": "pt-BR",
                "category": "Writing",
                "prompt": "simple request",
                "response_raw": "simple answer with matching content",
                "golden_response": "simple answer with matching content",
                "rubrics": rubrics,
                "metadata": {},
            },
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["structureValidation"]["status"], "pass")
        self.assertEqual(data["formatValidation"]["status"], "pass")
        self.assertEqual(data["qualityHeuristics"]["status"], "pass")
        self.assertEqual(data["qualityValidation"]["status"], "pending")

if __name__ == "__main__":
    unittest.main()
