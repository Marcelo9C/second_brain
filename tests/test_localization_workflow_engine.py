import unittest

from app.services.localization_workflow_engine import (
    ActionRouter,
    CaseStateEngine,
    CaseStateSnapshot,
    WorkflowDecisionEngine,
    WorkflowIntent,
)


def ready_snapshot(**overrides):
    payload = {
        "locale": "pt-BR",
        "category": "Writing",
        "prompt": "Synthetic prompt.",
        "response_raw": "Synthetic model response.",
        "golden_response": "Synthetic golden response.",
        "rubrics": [],
        "metadata": {},
    }
    payload.update(overrides)
    return CaseStateSnapshot.from_payload(payload)


class LocalizationWorkflowEngineTest(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = WorkflowDecisionEngine(
            case_state_engine=CaseStateEngine(),
            action_router=ActionRouter(),
        )

    def resolve(self, snapshot):
        return self.engine.resolve(WorkflowIntent.GENERATE_WITH_AI, snapshot)

    def test_empty_draft_is_not_ready_for_generation(self) -> None:
        decision = self.resolve(CaseStateSnapshot.from_payload({}))

        self.assertEqual(decision.decision, "not_ready")
        self.assertFalse(decision.model_call)
        self.assertIn("prompt", decision.missing_fields)

    def test_scaffold_without_real_case_is_not_ready_for_generation(self) -> None:
        decision = self.resolve(
            CaseStateSnapshot.from_payload(
                {
                    "locale": "pt-BR",
                    "category": "Writing",
                    "base_template": [{"slot": "synthetic"}],
                    "metadata": {"template_scaffold": {"template_name": "synthetic.json"}},
                }
            )
        )

        self.assertEqual(decision.decision, "not_ready")
        self.assertEqual(decision.reason, "template_scaffold_without_real_case_data")
        self.assertFalse(decision.model_call)

    def test_incomplete_case_reports_missing_fields(self) -> None:
        decision = self.resolve(ready_snapshot(response_raw="", golden_response=""))

        self.assertEqual(decision.decision, "not_ready")
        self.assertFalse(decision.model_call)
        self.assertEqual(decision.missing_fields, ["response_raw", "golden_response"])

    def test_rubrics_without_real_case_do_not_make_case_generatable(self) -> None:
        decision = self.resolve(
            CaseStateSnapshot.from_payload(
                {
                    "locale": "pt-BR",
                    "category": "Writing",
                    "rubrics": [{"partial": True}],
                    "metadata": {"rubric_source": "editor_draft"},
                }
            )
        )

        self.assertEqual(decision.decision, "not_ready")
        self.assertFalse(decision.model_call)
        self.assertIn("prompt", decision.missing_fields)

    def test_ready_case_can_execute_generation(self) -> None:
        decision = self.resolve(ready_snapshot())

        self.assertEqual(decision.decision, "execute_generation")
        self.assertTrue(decision.can_execute)
        self.assertTrue(decision.model_call)

    def test_template_scaffold_with_ready_case_can_execute_generation(self) -> None:
        decision = self.resolve(
            ready_snapshot(
                base_template=[{"slot": "synthetic"}],
                metadata={"template_scaffold": {"template_name": "synthetic.json"}},
            )
        )

        self.assertEqual(decision.decision, "execute_generation")
        self.assertTrue(decision.model_call)

    def test_mark_reviewed_requires_structure_and_format(self) -> None:
        not_ready = self.engine.resolve(WorkflowIntent.MARK_REVIEWED, ready_snapshot())
        ready = self.engine.resolve(
            WorkflowIntent.MARK_REVIEWED,
            ready_snapshot(
                validation_report={
                    "structureValidation": {"status": "pass"},
                    "formatValidation": {"status": "pass"},
                    "qualityValidation": {"status": "pending"},
                }
            ),
        )

        self.assertEqual(not_ready.decision, "not_ready")
        self.assertEqual(ready.decision, "execute")

    def test_approve_requires_approval_readiness(self) -> None:
        not_ready = self.engine.resolve(WorkflowIntent.APPROVE, ready_snapshot())
        ready = self.engine.resolve(
            WorkflowIntent.APPROVE,
            ready_snapshot(
                validation_report={
                    "approvalReadiness": {"status": "pass"},
                }
            ),
        )

        self.assertEqual(not_ready.decision, "not_ready")
        self.assertEqual(ready.decision, "execute")


if __name__ == "__main__":
    unittest.main()
