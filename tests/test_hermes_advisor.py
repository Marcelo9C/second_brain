import unittest

from app.schemas.hermes_advise import HermesAdviseRequest
from app.services.hermes.hermes_advisor import HermesAdvisor


class HermesAdvisorTest(unittest.TestCase):
    def setUp(self) -> None:
        self.advisor = HermesAdvisor()

    def advise(self, context: dict, objective: str = "generate_dpo_pairs"):
        request = HermesAdviseRequest(objective=objective, context=context)
        return self.advisor.advise(request)

    def advise_with_constraints(
        self,
        context: dict,
        constraints: dict,
        objective: str = "generate_dpo_pairs",
    ):
        request = HermesAdviseRequest(
            objective=objective,
            context=context,
            constraints=constraints,
        )
        return self.advisor.advise(request)

    def assert_recommendation(
        self,
        response,
        action: str,
        *,
        reason: str,
        confidence: float,
    ) -> None:
        recommendation = next(
            (item for item in response.recommendations if item.action == action),
            None,
        )
        self.assertIsNotNone(recommendation)
        self.assertEqual(recommendation.reason, reason)
        self.assertEqual(recommendation.selected_by, "recommendation")
        self.assertAlmostEqual(recommendation.confidence, confidence)
        self.assertTrue(recommendation.requires_confirmation)

    def test_same_generation_and_judge_model_recommends_diversity(self) -> None:
        response = self.advise(
            {
                "current_models": {
                    "generation": "llama3.2:3b",
                    "judge": "llama3.2:3b",
                }
            }
        )

        self.assert_recommendation(
            response,
            "diversify_model_families",
            reason="shared_family_may_reduce_judgment_independence",
            confidence=0.92,
        )
        self.assertEqual(response.diagnosis[0].issue, "generation_and_judge_model_coupling")
        self.assertEqual(response.proposed_plan[0].provenance["selected_by"], "recommendation")

    def test_weak_rubric_recommends_more_complexity(self) -> None:
        response = self.advise({"rubric": {"criteria_count": 2}})

        self.assert_recommendation(
            response,
            "increase_rubric_complexity",
            reason="low_criteria_may_reduce_signal_quality",
            confidence=0.88,
        )

    def test_low_margin_recommends_harder_prompt(self) -> None:
        response = self.advise(
            {
                "result": {"margin": 0.2},
                "current_thresholds": {"margin": 1.0},
            }
        )

        self.assert_recommendation(
            response,
            "rerun_with_harder_prompt",
            reason="insufficient_separation_between_candidates",
            confidence=0.9,
        )

    def test_single_turn_dataset_recommends_more_depth(self) -> None:
        response = self.advise({"num_conversations": 1, "num_turns": 1})

        self.assert_recommendation(
            response,
            "increase_run_depth_before_export",
            reason="single_turn_runs_are_smoke_tests_not_dataset_evidence",
            confidence=0.84,
        )

    def test_judge_conflict_recommends_human_review(self) -> None:
        response = self.advise({"judge_conflict": True})

        self.assert_recommendation(
            response,
            "send_pair_to_human_review",
            reason="judge_signal_conflict_requires_human_resolution",
            confidence=0.86,
        )

    def test_missing_margin_threshold_recommends_threshold_definition(self) -> None:
        response = self.advise({"result": {"margin": 0.7}})

        self.assert_recommendation(
            response,
            "define_margin_threshold",
            reason="preference_margin_without_threshold_blocks_reliable_acceptance",
            confidence=0.89,
        )

    def test_missing_model_provenance_recommends_provenance_recording(self) -> None:
        response = self.advise(
            {
                "model_provenance_required": True,
                "current_models": {
                    "generation": "llama3.2:3b",
                    "judge": "phi3:mini",
                },
                "model_provenance": {
                    "generation": {
                        "selected_by": "user",
                    }
                },
            }
        )

        self.assert_recommendation(
            response,
            "record_model_selection_provenance",
            reason="model_choices_need_selected_by_reason_and_confirmation_state",
            confidence=0.91,
        )

    def test_local_only_low_model_diversity_recommends_distinct_local_model(self) -> None:
        response = self.advise_with_constraints(
            {
                "available_models": ["llama3.2:3b"],
            },
            {
                "local_only": True,
            },
        )

        self.assert_recommendation(
            response,
            "add_distinct_local_model_before_judging",
            reason="local_only_constraint_has_insufficient_model_family_diversity",
            confidence=0.82,
        )

    def test_clean_context_has_no_recommendations(self) -> None:
        response = self.advise(
            {
                "current_models": {
                    "generation": "gemma4:e4b",
                    "judge": "phi3:mini",
                },
                "rubric": {"criteria_count": 4},
                "result": {"margin": 1.2},
                "current_thresholds": {"margin": 1.0},
                "num_conversations": 3,
                "num_turns": 2,
            }
        )

        self.assertEqual(response.recommendations, [])
        self.assertEqual(response.next_actions, [])


if __name__ == "__main__":
    unittest.main()
