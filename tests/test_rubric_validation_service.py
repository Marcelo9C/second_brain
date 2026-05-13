import unittest

from app.schemas.rubric_contract import RubricContract, RubricWeightPolicy
from app.services.rubric_validation_service import RubricValidationService


def valid_rubric() -> dict:
    return {
        "Rubric_dimensions": "Natural Language Fluency",
        "Rubric_title": "Clear Expression",
        "Rubrics_description": "The response is written clearly enough for an evaluator to assess.",
        "Rubrics_weight": 7,
        "is_response_specific": False,
    }


def valid_payload() -> dict:
    return {
        "locale": "pt-BR",
        "category": "Writing",
        "prompt": "Synthetic prompt.",
        "response_raw": "Synthetic raw response.",
        "golden_response": "Synthetic golden response.",
        "rubrics": [valid_rubric()],
        "metadata": {},
    }


def contract_for(*, dimension: str = "Natural Language Fluency", negative_min: int = -7, count: int = 1) -> dict:
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
        expected_rubric_count=count,
        negative_rubric_policy={"mode": "recommended"},
        requires_response_specific_when_context_exists=True,
        quality_review_required=True,
    ).model_dump(mode="json")


def contract_model(*, dimension: str = "Natural Language Fluency", negative_min: int = -7, count: int = 1) -> RubricContract:
    return RubricContract.model_validate(
        contract_for(dimension=dimension, negative_min=negative_min, count=count)
    )


class RubricValidationServiceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.service = RubricValidationService()

    def test_structure_fails_for_empty_rubrics(self) -> None:
        payload = valid_payload()
        payload["rubrics"] = []

        report = self.service.validate_case(payload)

        self.assertEqual(report["structureValidation"]["status"], "fail")
        self.assertEqual(report["approvalReadiness"]["status"], "blocked")

    def test_format_fails_for_bad_dimension(self) -> None:
        payload = valid_payload()
        payload["rubrics"][0]["Rubric_dimensions"] = "Unsupported Dimension"

        report = self.service.validate_case(payload)

        self.assertEqual(report["structureValidation"]["status"], "pass")
        self.assertEqual(report["formatValidation"]["status"], "fail")
        self.assertEqual(report["approvalReadiness"]["status"], "blocked")

    def test_format_fails_for_weight_below_negative_five(self) -> None:
        payload = valid_payload()
        payload["rubrics"][0]["Rubrics_weight"] = -6

        report = self.service.validate_case(payload)

        self.assertEqual(report["structureValidation"]["status"], "pass")
        self.assertEqual(report["formatValidation"]["status"], "fail")
        self.assertEqual(report["approvalReadiness"]["status"], "blocked")

    def test_service_uses_contract_when_provided_for_negative_weight(self) -> None:
        payload = valid_payload()
        payload["rubrics"][0]["Rubrics_weight"] = -7

        report = self.service.validate_case(
            payload,
            active_contract=contract_model(negative_min=-7),
        )

        self.assertEqual(report["structureValidation"]["status"], "pass")
        self.assertEqual(report["formatValidation"]["status"], "pass")

    def test_service_rejects_weight_outside_active_contract(self) -> None:
        payload = valid_payload()
        payload["rubrics"][0]["Rubrics_weight"] = -8

        report = self.service.validate_case(
            payload,
            active_contract=contract_model(negative_min=-7),
        )

        self.assertEqual(report["formatValidation"]["status"], "fail")
        self.assertIn("between -7 and -1", report["formatValidation"]["message"])

    def test_service_uses_contract_dimension_instead_of_global_whitelist(self) -> None:
        payload = valid_payload()
        payload["category"] = "Knowledge"
        payload["rubrics"][0]["Rubric_dimensions"] = "Facts and Local Knowledge"
        payload["rubrics"][0]["Rubrics_weight"] = -10

        report = self.service.validate_case(
            payload,
            active_contract=contract_model(
                dimension="Facts and Local Knowledge",
                negative_min=-10,
            ),
        )

        self.assertEqual(report["formatValidation"]["status"], "pass")

    def test_recommended_negative_policy_does_not_block_approval_without_negative_rubric(self) -> None:
        payload = valid_payload()
        payload["metadata"] = {"human_quality_reviewed": True}

        report = self.service.validate_case(
            payload,
            active_contract=contract_model(negative_min=-7),
        )

        self.assertEqual(report["formatValidation"]["status"], "pass")
        self.assertEqual(report["qualityValidation"]["status"], "pass")
        self.assertEqual(report["approvalReadiness"]["status"], "pass")

    def test_contract_expected_count_is_warning_not_approval_block(self) -> None:
        payload = valid_payload()
        payload["metadata"] = {"human_quality_reviewed": True}

        report = self.service.validate_case(
            payload,
            active_contract=contract_model(negative_min=-7, count=5),
        )

        self.assertEqual(report["qualityHeuristics"]["status"], "warning")
        self.assertEqual(report["qualityHeuristics"]["signals"]["count_coverage_status"], "under_generated")
        self.assertFalse(report["qualityHeuristics"]["blocking"])
        self.assertEqual(report["qualityValidation"]["status"], "pass")
        self.assertEqual(report["approvalReadiness"]["status"], "pass")

    def test_quality_is_pending_by_default(self) -> None:
        report = self.service.validate_case(valid_payload())

        self.assertEqual(report["structureValidation"]["status"], "pass")
        self.assertEqual(report["formatValidation"]["status"], "pass")
        self.assertEqual(report["qualityHeuristics"]["status"], "warning")
        self.assertFalse(report["qualityHeuristics"]["blocking"])
        self.assertEqual(report["qualityValidation"]["status"], "pending")
        self.assertEqual(report["approvalReadiness"]["status"], "blocked")

    def test_schema_valid_rubrics_can_have_quality_warnings(self) -> None:
        payload = valid_payload()
        payload["rubrics"] = [
            {
                "Rubric_dimensions": "Natural Language Fluency",
                "Rubric_title": "Natural Tone",
                "Rubrics_description": "The response uses natural language suitable for the request.",
                "Rubrics_weight": 9,
                "is_response_specific": False,
            },
            {
                "Rubric_dimensions": "Natural Language Fluency",
                "Rubric_title": "Conversational Tone",
                "Rubrics_description": "The response uses conversational language suitable for the request.",
                "Rubrics_weight": 9,
                "is_response_specific": False,
            },
            {
                "Rubric_dimensions": "Natural Language Fluency",
                "Rubric_title": "Clear Wording",
                "Rubrics_description": "The response uses clear wording suitable for evaluation.",
                "Rubrics_weight": 9,
                "is_response_specific": False,
            },
            {
                "Rubric_dimensions": "Natural Language Fluency",
                "Rubric_title": "Readable Flow",
                "Rubrics_description": "The response has readable flow and direct phrasing.",
                "Rubrics_weight": 8,
                "is_response_specific": False,
            },
        ]

        report = self.service.validate_case(payload)

        self.assertEqual(report["structureValidation"]["status"], "pass")
        self.assertEqual(report["formatValidation"]["status"], "pass")
        self.assertEqual(report["qualityHeuristics"]["status"], "warning")
        self.assertFalse(report["qualityHeuristics"]["blocking"])
        self.assertIn("Only 4 rubrics generated", " ".join(report["qualityHeuristics"]["messages"]))

    def test_approval_passes_after_human_quality_review(self) -> None:
        payload = valid_payload()
        payload["metadata"] = {"human_quality_reviewed": True}

        report = self.service.validate_case(payload)

        self.assertEqual(report["qualityValidation"]["status"], "pass")
        self.assertEqual(report["approvalReadiness"]["status"], "pass")

    def test_approval_blocks_when_case_fields_are_missing(self) -> None:
        payload = valid_payload()
        payload["metadata"] = {"human_quality_reviewed": True}
        payload["golden_response"] = ""

        report = self.service.validate_case(payload)

        self.assertEqual(report["qualityValidation"]["status"], "pass")
        self.assertEqual(report["approvalReadiness"]["status"], "blocked")
        self.assertIn("golden_response", report["approvalReadiness"]["missing_fields"])

    def test_reviewed_requires_human_quality_review(self) -> None:
        with self.assertRaises(ValueError):
            self.service.assert_can_use_status(valid_payload(), "reviewed")

    def test_approved_requires_approval_readiness(self) -> None:
        payload = valid_payload()
        payload["metadata"] = {"human_quality_reviewed": True}
        payload["prompt"] = ""

        with self.assertRaises(ValueError):
            self.service.assert_can_use_status(payload, "approved")


if __name__ == "__main__":
    unittest.main()
