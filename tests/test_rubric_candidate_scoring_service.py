import json
import unittest

from app.services.providers.base_provider import BaseProvider, ProviderError, ProviderPrompt, ProviderResult
from app.services.rubric_candidate_scoring_service import RubricCandidateScoringService


def rubric(title: str, weight: int) -> dict:
    return {
        "Rubric_dimensions": "Natural Language Fluency",
        "Rubric_title": title,
        "Rubrics_description": "Synthetic rubric description for candidate scoring.",
        "Rubrics_weight": weight,
        "is_response_specific": False,
    }


def scoring_payload(**overrides):
    payload = {
        "locale": "pt-BR",
        "category": "Writing",
        "prompt": "Synthetic prompt.",
        "golden_response": "Synthetic golden response.",
        "rubrics": [
            rubric("Structure", 10),
            rubric("Unsupported Claim Penalty", -6),
        ],
        "candidate_responses": [
            {"id": "A", "label": "Candidate A", "response_raw": "Clear structured answer."},
            {"id": "B", "label": "Candidate B", "response_raw": "Answer with unsupported claim."},
        ],
        "provider": "fake",
        "model": "fake-model",
    }
    payload.update(overrides)
    return payload


class FakeScoringProvider(BaseProvider):
    name = "fake"
    label = "Fake Provider"
    implemented = True

    def __init__(
        self,
        *,
        response_text: str | None = None,
        fail: bool = False,
        force_model_used: str | None = None,
    ) -> None:
        self.response_text = response_text
        self.fail = fail
        self.force_model_used = force_model_used
        self.calls = 0
        self.last_prompt = None

    def list_models(self) -> list[dict]:
        return [{"name": "fake-model"}]

    def generate(self, *, prompt: ProviderPrompt | str, model: str | None = None) -> ProviderResult:
        self.calls += 1
        self.last_prompt = prompt
        if self.fail:
            raise ProviderError("Synthetic scoring failure.")
        return ProviderResult(
            text=self.response_text
            if self.response_text is not None
            else json.dumps(
                {
                    "candidate_scores": [
                        {
                            "candidate_id": "A",
                            "rubric_scores": [
                                {
                                    "rubric_index": 1,
                                    "score_factor": 1,
                                    "judgment": "met",
                                    "rationale": "Well structured.",
                                },
                                {
                                    "rubric_index": 2,
                                    "score_factor": 0,
                                    "judgment": "not_met",
                                    "rationale": "No unsupported claim.",
                                },
                            ],
                        },
                        {
                            "candidate_id": "B",
                            "rubric_scores": [
                                {
                                    "rubric_index": 1,
                                    "score_factor": 0.5,
                                    "judgment": "partial",
                                    "rationale": "Partly structured.",
                                },
                                {
                                    "rubric_index": 2,
                                    "score_factor": 1,
                                    "judgment": "met",
                                    "rationale": "Penalty applies.",
                                },
                            ],
                        },
                    ]
                }
            ),
            provider_used="fake",
            model_used=self.force_model_used or model or "fake-model",
            exact_url_called="http://fake.local/generate",
            response_status=200,
            duration_ms=1,
        )


class RubricCandidateScoringServiceTest(unittest.TestCase):
    def service(self, provider: FakeScoringProvider) -> RubricCandidateScoringService:
        return RubricCandidateScoringService(
            providers={"fake": provider},
            default_provider="fake",
        )

    def test_scores_candidates_and_returns_preference(self) -> None:
        result = self.service(FakeScoringProvider()).score(scoring_payload())

        self.assertTrue(result["success"])
        self.assertEqual(result["candidate_scores"][0]["candidate_id"], "A")
        self.assertEqual(result["candidate_scores"][0]["total_score"], 10)
        self.assertEqual(result["candidate_scores"][1]["total_score"], -1)
        self.assertEqual(result["preference"]["chosen_candidate_id"], "A")
        self.assertEqual(result["preference"]["rejected_candidate_id"], "B")
        self.assertEqual(result["preference"]["margin"], 11)

    def test_prompt_describes_negative_weight_semantics(self) -> None:
        provider = FakeScoringProvider()

        self.service(provider).score(scoring_payload())

        prompt = provider.last_prompt.as_text()
        self.assertIn("For negative-weight rubrics", prompt)
        self.assertIn("score_factor 1 means the penalty fully applies", prompt)

    def test_rejects_missing_candidate_score(self) -> None:
        provider = FakeScoringProvider(
            response_text=json.dumps(
                {
                    "candidate_scores": [
                        {
                            "candidate_id": "A",
                            "rubric_scores": [
                                {
                                    "rubric_index": 1,
                                    "score_factor": 1,
                                    "judgment": "met",
                                    "rationale": "Only one rubric.",
                                },
                                {
                                    "rubric_index": 2,
                                    "score_factor": 0,
                                    "judgment": "not_met",
                                    "rationale": "No penalty.",
                                },
                            ],
                        }
                    ]
                }
            )
        )

        result = self.service(provider).score(scoring_payload())

        self.assertFalse(result["success"])
        self.assertEqual(result["metadata"]["scoring_failure_type"], "invalid_scoring_response")
        self.assertIn("missing candidates", result["warnings"][0])

    def test_model_mismatch_discards_result(self) -> None:
        result = self.service(FakeScoringProvider(force_model_used="fallback-model")).score(scoring_payload())

        self.assertFalse(result["success"])
        self.assertEqual(result["metadata"]["scoring_failure_type"], "provider_mismatch_discarded")
        self.assertTrue(result["metadata"]["result_discarded"])

    def test_provider_failure_returns_success_false(self) -> None:
        result = self.service(FakeScoringProvider(fail=True)).score(scoring_payload())

        self.assertFalse(result["success"])
        self.assertEqual(result["metadata"]["scoring_failure_type"], "provider_failed")
        self.assertEqual(result["metadata"]["raw_error"], "Synthetic scoring failure.")


if __name__ == "__main__":
    unittest.main()
