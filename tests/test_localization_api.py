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
    ) -> None:
        self.name = name
        self.label = f"{name} Provider"
        self.fail = fail
        self.calls = 0
        self.force_model_used = force_model_used
        self.force_provider_used = force_provider_used
        self.models = models or ["fake-model", "fake-default"]
        self.default_model_name = default_model_name

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
            text=json.dumps(rubrics),
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
        self.assertEqual(data["metadata"]["blocked_reason"], "provider_executed_different_model")
        self.assertIsNone(data.get("rubrics"))
        self.assertIsNone(data.get("raw_model_response"))

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

if __name__ == "__main__":
    unittest.main()
