import json
import unittest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock

from app.main import app
from app.dependencies import get_rubric_generation_service
from app.schemas.rubric_contract import RubricContract, RubricWeightPolicy
from app.services.candidate_recommendation_service import CandidateRecommendationService
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
        self.last_prompt = None

    def list_models(self) -> list[dict]:
        return [{"name": model} for model in self.models]

    def default_model(self) -> str | None:
        return self.default_model_name

    def generate(self, *, prompt: ProviderPrompt | str, model: str | None = None) -> ProviderResult:
        self.calls += 1
        self.last_prompt = prompt
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

    def _contract(
        self,
        *,
        dimension: str,
        negative_min: int,
        expected_rubric_count: int = 1,
    ) -> dict:
        return RubricContract(
            allowed_dimensions=[dimension],
            weight_policy=RubricWeightPolicy(
                positive_min=1,
                positive_max=10,
                negative_min=negative_min,
                negative_max=-1,
                zero_allowed=False,
                integer_only=True,
            ),
            expected_rubric_count=expected_rubric_count,
            negative_rubric_policy={"mode": "recommended"},
            requires_response_specific_when_context_exists=True,
            quality_review_required=True,
        ).model_dump(mode="json")

    def _rubric(self, *, dimension: str, weight: int, title: str = "Synthetic") -> dict:
        return {
            "Rubric_dimensions": dimension,
            "Rubric_title": title,
            "Rubrics_description": "Synthetic rubric description for API contract validation.",
            "Rubrics_weight": weight,
            "is_response_specific": False,
        }

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

    def test_chitchat_contract_allows_negative_six_generation(self):
        rubrics = [
            self._rubric(dimension="Natural Language Fluency", weight=8, title="Natural Tone"),
            self._rubric(dimension="Cultural Understanding and Application", weight=8, title="Tone Alignment"),
            self._rubric(dimension="Natural Language Fluency", weight=7, title="Informal Language"),
            self._rubric(dimension="Cultural Understanding and Application", weight=7, title="Social Awareness"),
            self._rubric(dimension="Natural Language Fluency", weight=-6, title="Scripted Tone"),
        ]
        self.fake_provider.response_text = json.dumps(rubrics)

        response = self.client.post(
            "/api/localization/rubrics/generate",
            json=self._ready_payload(
                category="Chitchat",
                base_template=rubrics,
                model="fake-model",
            ),
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["metadata"]["validation_status"], "valid")

    def test_knowledge_contract_allows_negative_ten_generation(self):
        rubrics = [
            self._rubric(dimension="Facts and Local Knowledge", weight=10, title="Factual Accuracy"),
            self._rubric(dimension="Facts and Local Knowledge", weight=10, title="Intent Interpretation"),
            self._rubric(dimension="Facts and Local Knowledge", weight=8, title="Explanation Depth"),
            self._rubric(dimension="Cultural Understanding and Application", weight=7, title="Actionable Guidance"),
            self._rubric(dimension="Facts and Local Knowledge", weight=-10, title="Fabrication"),
            self._rubric(dimension="Facts and Local Knowledge", weight=-10, title="Misinterpretation"),
        ]
        self.fake_provider.response_text = json.dumps(rubrics)

        response = self.client.post(
            "/api/localization/rubrics/generate",
            json=self._ready_payload(
                category="Knowledge",
                base_template=rubrics,
                model="fake-model",
            ),
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["metadata"]["validation_status"], "valid")

    def test_adulterated_negative_min_contract_does_not_relax_generation_validation(self):
        rubrics = [
            self._rubric(dimension="Natural Language Fluency", weight=8, title="Natural Tone"),
            self._rubric(dimension="Cultural Understanding and Application", weight=8, title="Tone Alignment"),
            self._rubric(dimension="Natural Language Fluency", weight=7, title="Informal Language"),
            self._rubric(dimension="Cultural Understanding and Application", weight=7, title="Social Awareness"),
            self._rubric(dimension="Natural Language Fluency", weight=-7, title="Scripted Tone"),
        ]
        self.fake_provider.response_text = json.dumps(rubrics)
        adulterated_contract = self._contract(
            dimension="Natural Language Fluency",
            negative_min=-99,
            expected_rubric_count=5,
        )

        response = self.client.post(
            "/api/localization/rubrics/generate",
            json=self._ready_payload(
                category="Chitchat",
                base_template=rubrics,
                contract=adulterated_contract,
                model="fake-model",
            ),
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("contract_mismatch", response.json()["detail"])

    def test_adulterated_dimension_contract_does_not_replace_formal_contract(self):
        rubrics = [
            self._rubric(dimension="Local Facts and Awareness", weight=10, title="Altered Dimension"),
            self._rubric(dimension="Facts and Local Knowledge", weight=10, title="Intent Interpretation"),
            self._rubric(dimension="Facts and Local Knowledge", weight=8, title="Explanation Depth"),
            self._rubric(dimension="Cultural Understanding and Application", weight=7, title="Actionable Guidance"),
            self._rubric(dimension="Facts and Local Knowledge", weight=-10, title="Fabrication"),
            self._rubric(dimension="Facts and Local Knowledge", weight=-10, title="Misinterpretation"),
        ]
        self.fake_provider.response_text = json.dumps(rubrics)
        adulterated_contract = self._contract(
            dimension="Local Facts and Awareness",
            negative_min=-10,
            expected_rubric_count=6,
        )

        response = self.client.post(
            "/api/localization/rubrics/generate",
            json=self._ready_payload(
                category="Knowledge",
                base_template=rubrics,
                contract=adulterated_contract,
                model="fake-model",
            ),
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("contract_mismatch", response.json()["detail"])

    def test_formal_contract_error_message_wins_without_payload_contract(self):
        rubrics = [
            self._rubric(dimension="Natural Language Fluency", weight=8, title="Natural Tone"),
            self._rubric(dimension="Cultural Understanding and Application", weight=8, title="Tone Alignment"),
            self._rubric(dimension="Natural Language Fluency", weight=7, title="Informal Language"),
            self._rubric(dimension="Cultural Understanding and Application", weight=7, title="Social Awareness"),
            self._rubric(dimension="Natural Language Fluency", weight=-7, title="Scripted Tone"),
        ]
        self.fake_provider.response_text = json.dumps(rubrics)

        response = self.client.post(
            "/api/localization/rubrics/generate",
            json=self._ready_payload(
                category="Chitchat",
                base_template=rubrics,
                model="fake-model",
            ),
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertFalse(data["success"])
        self.assertEqual(data["metadata"]["validation_status"], "failed")
        self.assertIn("between -6 and -1", data["metadata"]["validation_error"])

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

    def test_legacy_response_raw_still_generates(self):
        response = self.client.post(
            "/api/localization/rubrics/generate",
            json=self._ready_payload(model="fake-model"),
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["metadata"]["candidate_count"], 0)
        self.assertEqual(
            data["metadata"]["response_raw_resolution"]["mode"],
            "legacy_response_raw",
        )

    def test_candidate_response_payload_generates_with_selected_candidate_only(self):
        response = self.client.post(
            "/api/localization/rubrics/generate",
            json=self._ready_payload(
                response_raw="Stale legacy response.",
                candidate_responses=[
                    {"id": "A", "label": "Candidate A", "response_raw": "Unselected A response."},
                    {"id": "B", "label": "Candidate B", "response_raw": "Selected B response."},
                ],
                selected_candidate_id="B",
                model="fake-model",
            ),
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["metadata"]["selected_candidate_id"], "B")
        self.assertEqual(data["metadata"]["selected_candidate_label"], "Candidate B")
        self.assertEqual(data["metadata"]["candidate_count"], 2)
        prompt_text = self.fake_provider.last_prompt.as_text()
        self.assertIn('"response_raw": "Selected B response."', prompt_text)
        self.assertNotIn("Unselected A response.", prompt_text)
        self.assertNotIn("Stale legacy response.", prompt_text)

    def test_candidate_response_missing_selection_is_rejected(self):
        response = self.client.post(
            "/api/localization/rubrics/generate",
            json=self._ready_payload(
                candidate_responses=[
                    {"id": "A", "response_raw": "Candidate A response."},
                ],
                model="fake-model",
            ),
        )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(self.fake_provider.calls, 0)

    def test_candidate_response_unknown_selection_is_rejected(self):
        response = self.client.post(
            "/api/localization/rubrics/generate",
            json=self._ready_payload(
                candidate_responses=[
                    {"id": "A", "response_raw": "Candidate A response."},
                ],
                selected_candidate_id="B",
                model="fake-model",
            ),
        )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(self.fake_provider.calls, 0)

    def test_recommend_golden_endpoint_returns_valid_recommendation(self):
        self.fake_provider.response_text = json.dumps(
            {
                "recommended_candidate_id": "B",
                "reason": "Candidate B is clearer.",
                "warnings": [],
            }
        )
        service = CandidateRecommendationService(
            providers={"fake": self.fake_provider},
            default_provider="fake",
        )

        with patch("app.api.routes.localization.get_candidate_recommendation_service", return_value=service):
            response = self.client.post(
                "/api/localization/candidate-responses/recommend-golden",
                json={
                    "locale": "pt-BR",
                    "category": "Writing",
                    "prompt": "Synthetic prompt.",
                    "candidate_responses": [
                        {"id": "A", "label": "Candidate A", "response_raw": "A response."},
                        {"id": "B", "label": "Candidate B", "response_raw": "B response."},
                    ],
                    "provider": "fake",
                    "model": "fake-model",
                },
            )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["recommended_candidate_id"], "B")
        self.assertEqual(data["recommended_candidate_label"], "Candidate B")
        self.assertNotIn("rubrics", data)
        self.assertEqual(data["metadata"]["provider_requested"], "fake")
        self.assertEqual(data["metadata"]["model_requested"], "fake-model")
        self.assertEqual(data["metadata"]["provider_used"], "fake")
        self.assertEqual(data["metadata"]["model_used"], "fake-model")
        self.assertEqual(data["metadata"]["candidate_count"], 2)

    def test_recommend_golden_endpoint_provider_failure_returns_success_false(self):
        self.fake_provider.fail = True
        service = CandidateRecommendationService(
            providers={"fake": self.fake_provider},
            default_provider="fake",
        )

        with patch("app.api.routes.localization.get_candidate_recommendation_service", return_value=service):
            response = self.client.post(
                "/api/localization/candidate-responses/recommend-golden",
                json={
                    "locale": "pt-BR",
                    "category": "Writing",
                    "prompt": "Synthetic prompt.",
                    "candidate_responses": [{"id": "A", "response_raw": "A response."}],
                    "provider": "fake",
                    "model": "fake-model",
                },
            )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertFalse(data["success"])
        self.assertEqual(data["metadata"]["generation_failure_type"], "provider_failed")

    def test_recommend_golden_debug_false_hides_trace_payload(self):
        self.fake_provider.response_text = json.dumps(
            {
                "recommended_candidate_id": "C",
                "reason": "No match.",
                "warnings": [],
            }
        )
        service = CandidateRecommendationService(
            providers={"fake": self.fake_provider},
            default_provider="fake",
            debug_trace=False,
        )

        with patch("app.api.routes.localization.get_candidate_recommendation_service", return_value=service):
            response = self.client.post(
                "/api/localization/candidate-responses/recommend-golden",
                json={
                    "locale": "pt-BR",
                    "category": "Writing",
                    "prompt": "Synthetic prompt.",
                    "candidate_responses": [
                        {"id": "A", "label": "Candidate A", "response_raw": "A response."},
                        {"id": "B", "label": "Candidate B", "response_raw": "B response."},
                    ],
                    "provider": "fake",
                    "model": "fake-model",
                },
            )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertFalse(data["success"])
        self.assertEqual(data["metadata"]["generation_failure_type"], "invalid_recommendation_response")
        self.assertNotIn("recommendation_trace", data["metadata"])
        self.assertNotIn("raw_provider_response", data["metadata"])
        self.assertEqual(
            data["warnings"],
            ["A IA não retornou uma candidata válida. Tente novamente ou selecione uma candidata manualmente."],
        )

    def test_recommend_golden_debug_true_exposes_trace(self):
        raw_response = json.dumps(
            {
                "recommended_candidate_id": "C",
                "reason": "No match.",
                "warnings": [],
            }
        )
        self.fake_provider.response_text = raw_response
        service = CandidateRecommendationService(
            providers={"fake": self.fake_provider},
            default_provider="fake",
            debug_trace=True,
        )

        with patch("app.api.routes.localization.get_candidate_recommendation_service", return_value=service):
            response = self.client.post(
                "/api/localization/candidate-responses/recommend-golden",
                json={
                    "locale": "pt-BR",
                    "category": "Writing",
                    "prompt": "Synthetic prompt.",
                    "candidate_responses": [
                        {"id": "A", "label": "Candidate A", "response_raw": "A response."},
                        {"id": "B", "label": "Candidate B", "response_raw": "B response."},
                    ],
                    "provider": "fake",
                    "model": "fake-model",
                },
            )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        trace = data["metadata"]["recommendation_trace"]
        self.assertFalse(data["success"])
        self.assertEqual(trace["raw_provider_response"], raw_response)
        self.assertEqual(trace["parsed_response"]["recommended_candidate_id"], "C")
        self.assertEqual(
            trace["validation_error"],
            "recommended_candidate_id does not match any submitted candidate.",
        )
        self.assertEqual(trace["endpoint_response"]["metadata"]["generation_failure_type"], "invalid_recommendation_response")

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
                "Rubrics_description": "Rewards concise wording, plain syntax, and readable sentence flow.",
                "Rubrics_weight": 7,
                "is_response_specific": False,
            },
            {
                "Rubric_dimensions": "Natural Language Fluency",
                "Rubric_title": "Structure Fit",
                "Rubrics_description": "Checks that the response organization matches the requested task shape.",
                "Rubrics_weight": 6,
                "is_response_specific": False,
            },
            {
                "Rubric_dimensions": "Cultural Understanding and Application",
                "Rubric_title": "Audience Fit",
                "Rubrics_description": "Rewards register choices that suit the intended reader and situation.",
                "Rubrics_weight": 5,
                "is_response_specific": False,
            },
            {
                "Rubric_dimensions": "Natural Language Fluency",
                "Rubric_title": "Grounded Claim Handling",
                "Rubrics_description": "Checks that factual statements remain scoped to provided information.",
                "Rubrics_weight": 4,
                "is_response_specific": False,
            },
            {
                "Rubric_dimensions": "Cultural Understanding and Application",
                "Rubric_title": "Unsupported Addition Penalty",
                "Rubrics_description": "Penalizes invented context, extra commitments, or unsupported assumptions.",
                "Rubrics_weight": -3,
                "is_response_specific": False,
            },
            {
                "Rubric_dimensions": "Cultural Understanding and Application",
                "Rubric_title": "Context Fit",
                "Rubrics_description": "Rewards choices that stay appropriate for the simple synthetic scenario.",
                "Rubrics_weight": 3,
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
