import unittest

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

    def test_quality_is_pending_by_default(self) -> None:
        report = self.service.validate_case(valid_payload())

        self.assertEqual(report["structureValidation"]["status"], "pass")
        self.assertEqual(report["formatValidation"]["status"], "pass")
        self.assertEqual(report["qualityValidation"]["status"], "pending")
        self.assertEqual(report["approvalReadiness"]["status"], "blocked")

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
