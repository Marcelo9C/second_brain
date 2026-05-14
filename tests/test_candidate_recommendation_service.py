import json
import unittest

from app.services.candidate_recommendation_service import CandidateRecommendationService
from app.services.providers.base_provider import BaseProvider, ProviderError, ProviderPrompt, ProviderResult


def recommendation_payload(**overrides):
    payload = {
        "locale": "pt-BR",
        "category": "Writing",
        "prompt": "Synthetic prompt.",
        "candidate_responses": [
            {"id": "A", "label": "Candidate A", "response_raw": "Adequate but terse."},
            {"id": "B", "label": "Candidate B", "response_raw": "Clear, complete response."},
        ],
        "provider": "fake",
        "model": "fake-model",
    }
    payload.update(overrides)
    return payload


class FakeRecommendationProvider(BaseProvider):
    name = "fake"
    label = "Fake Provider"
    implemented = True

    def __init__(
        self,
        *,
        fail: bool = False,
        response_text: str | None = None,
        force_model_used: str | None = None,
        force_provider_used: str | None = None,
    ) -> None:
        self.fail = fail
        self.response_text = response_text
        self.force_model_used = force_model_used
        self.force_provider_used = force_provider_used
        self.calls = 0
        self.last_prompt = None

    def list_models(self) -> list[dict]:
        return [{"name": "fake-model"}]

    def generate(self, *, prompt: ProviderPrompt | str, model: str | None = None) -> ProviderResult:
        self.calls += 1
        self.last_prompt = prompt
        if self.fail:
            raise ProviderError("Synthetic provider failure.")
        return ProviderResult(
            text=self.response_text
            if self.response_text is not None
            else json.dumps(
                {
                    "recommended_candidate_id": "B",
                    "reason": "Candidate B is clearer and easier to edit.",
                    "warnings": [],
                }
            ),
            provider_used=self.force_provider_used or "fake",
            model_used=self.force_model_used or model or "fake-model",
            exact_url_called="http://fake.local/generate",
            response_status=200,
            duration_ms=1,
        )


class CandidateRecommendationServiceTest(unittest.TestCase):
    def service(self, provider: FakeRecommendationProvider) -> CandidateRecommendationService:
        return CandidateRecommendationService(providers={"fake": provider}, default_provider="fake")

    def test_request_with_one_valid_candidate_returns_recommendation(self) -> None:
        provider = FakeRecommendationProvider(
            response_text=json.dumps({"recommended_candidate_id": "A", "reason": "Best base.", "warnings": []})
        )

        result = self.service(provider).recommend(
            recommendation_payload(candidate_responses=[{"id": "A", "response_raw": "Only candidate."}])
        )

        self.assertTrue(result["success"])
        self.assertEqual(result["recommended_candidate_id"], "A")
        self.assertEqual(result["recommended_candidate_label"], "Candidate A")
        self.assertEqual(result["metadata"]["candidate_count"], 1)

    def test_request_with_four_candidates_is_accepted(self) -> None:
        provider = FakeRecommendationProvider(
            response_text=json.dumps({"recommended_candidate_id": "D", "reason": "Best base.", "warnings": []})
        )

        result = self.service(provider).recommend(
            recommendation_payload(
                candidate_responses=[
                    {"id": "A", "response_raw": "A response."},
                    {"id": "B", "response_raw": "B response."},
                    {"id": "C", "response_raw": "C response."},
                    {"id": "D", "response_raw": "D response."},
                ]
            )
        )

        self.assertTrue(result["success"])
        self.assertEqual(result["recommended_candidate_id"], "D")
        self.assertEqual(result["metadata"]["candidate_count"], 4)

    def test_recommendation_id_accepts_candidate_label_variants(self) -> None:
        variants = ["Candidate B", "Candidata B", "Candidato B", "candidate-B", "candidate_B"]

        for variant in variants:
            with self.subTest(variant=variant):
                provider = FakeRecommendationProvider(
                    response_text=json.dumps(
                        {
                            "recommended_candidate_id": variant,
                            "reason": "Best base.",
                            "warnings": [],
                        }
                    )
                )

                result = self.service(provider).recommend(recommendation_payload())

                self.assertTrue(result["success"])
                self.assertEqual(result["recommended_candidate_id"], "B")

    def test_recommendation_id_outside_submitted_candidates_is_rejected(self) -> None:
        provider = FakeRecommendationProvider(
            response_text=json.dumps(
                {
                    "recommended_candidate_id": "Candidato D",
                    "reason": "No submitted match.",
                    "warnings": [],
                }
            )
        )

        result = self.service(provider).recommend(recommendation_payload())

        self.assertFalse(result["success"])
        self.assertEqual(result["metadata"]["generation_failure_type"], "invalid_recommendation_response")
        self.assertIsNone(result["recommended_candidate_id"])

    def test_ambiguous_recommendation_id_is_rejected(self) -> None:
        provider = FakeRecommendationProvider(
            response_text=json.dumps(
                {
                    "recommended_candidate_id": "Candidate A or B",
                    "reason": "Ambiguous.",
                    "warnings": [],
                }
            )
        )

        result = self.service(provider).recommend(recommendation_payload())

        self.assertFalse(result["success"])
        self.assertEqual(result["metadata"]["generation_failure_type"], "invalid_recommendation_response")

    def test_provider_failure_returns_success_false(self) -> None:
        result = self.service(FakeRecommendationProvider(fail=True)).recommend(recommendation_payload())

        self.assertFalse(result["success"])
        self.assertIsNone(result["recommended_candidate_id"])
        self.assertEqual(result["metadata"]["generation_failure_type"], "provider_failed")
        self.assertEqual(result["metadata"]["raw_error"], "Synthetic provider failure.")

    def test_invalid_recommendation_id_is_rejected(self) -> None:
        provider = FakeRecommendationProvider(
            response_text=json.dumps({"recommended_candidate_id": "D", "reason": "No match.", "warnings": []})
        )

        result = self.service(provider).recommend(recommendation_payload())

        self.assertFalse(result["success"])
        self.assertEqual(result["metadata"]["generation_failure_type"], "invalid_recommendation_response")
        self.assertIsNone(result["recommended_candidate_id"])

    def test_provider_model_mismatch_is_discarded(self) -> None:
        provider = FakeRecommendationProvider(force_model_used="fallback-model")

        result = self.service(provider).recommend(recommendation_payload())

        self.assertFalse(result["success"])
        self.assertEqual(result["metadata"]["generation_failure_type"], "provider_mismatch_discarded")
        self.assertTrue(result["metadata"]["result_discarded"])

    def test_metadata_records_provider_model_and_candidate_count(self) -> None:
        result = self.service(FakeRecommendationProvider()).recommend(recommendation_payload())

        self.assertTrue(result["success"])
        self.assertEqual(result["metadata"]["provider_requested"], "fake")
        self.assertEqual(result["metadata"]["model_requested"], "fake-model")
        self.assertEqual(result["metadata"]["provider_used"], "fake")
        self.assertEqual(result["metadata"]["model_used"], "fake-model")
        self.assertEqual(result["metadata"]["candidate_count"], 2)

    def test_prompt_does_not_ask_for_rubrics_or_confidential_guidelines(self) -> None:
        provider = FakeRecommendationProvider()

        self.service(provider).recommend(recommendation_payload())

        prompt = provider.last_prompt.as_text()
        self.assertIn("Do not write rubrics", prompt)
        self.assertIn("Do not finalize the Golden Response", prompt)
        self.assertIn("Do not use confidential guidelines", prompt)
        self.assertNotIn("Rubric_dimensions", prompt)


if __name__ == "__main__":
    unittest.main()
