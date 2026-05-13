import unittest
from unittest.mock import patch

from fastapi import HTTPException
from pydantic import ValidationError

from app.api.routes import localization as localization_routes
from app.schemas.localization import RubricCaseCreate, RubricCaseUpdate, validate_rubric_payload
from app.schemas.rubric_contract import RubricContract, RubricWeightPolicy


class BlockingService:
    def update_case(self, case_id: str, payload: dict) -> dict:
        raise ValueError("Status approved blocked: approval readiness is not pass.")


class LocalizationSchemaTest(unittest.TestCase):
    def test_draft_allows_incomplete_rubrics(self) -> None:
        case = RubricCaseCreate(
            category="Writing",
            template_name="synthetic_template.json",
            status="draft",
            rubrics=[{"partial": True}],
        )

        self.assertEqual(case.status, "draft")
        self.assertEqual(case.rubrics, [{"partial": True}])

    def test_approved_requires_structured_rubrics(self) -> None:
        with self.assertRaises(ValidationError):
            RubricCaseCreate(
                category="Writing",
                template_name="synthetic_template.json",
                status="approved",
                rubrics=[],
            )

    def test_partial_draft_update_allows_incomplete_rubrics_without_status(self) -> None:
        update = RubricCaseUpdate(rubrics=[{"partial": True}])

        self.assertIsNone(update.status)
        self.assertEqual(update.rubrics, [{"partial": True}])

    def test_approved_update_block_returns_controlled_http_error(self) -> None:
        payload = RubricCaseUpdate(status="approved", rubrics=[{"partial": True}])

        with patch.object(localization_routes, "get_localization_service", return_value=BlockingService()):
            with self.assertRaises(HTTPException) as error:
                localization_routes.update_rubric_case("synthetic-id", payload)

        self.assertEqual(error.exception.status_code, 400)
        self.assertIn("approval readiness", error.exception.detail)

    def test_validate_rubric_payload_uses_received_contract(self) -> None:
        contract = RubricContract(
            allowed_dimensions=["Facts and Local Knowledge"],
            weight_policy=RubricWeightPolicy(
                positive_min=1,
                positive_max=10,
                negative_min=-10,
                negative_max=-1,
                zero_allowed=False,
                integer_only=True,
            ),
            expected_rubric_count=1,
            requires_negative_rubric=True,
            requires_response_specific_when_context_exists=True,
            quality_review_required=True,
        )
        rubrics = [
            {
                "Rubric_dimensions": "Facts and Local Knowledge",
                "Rubric_title": "Factual Accuracy",
                "Rubrics_description": "The response avoids fabricated or unsupported information.",
                "Rubrics_weight": -10,
                "is_response_specific": False,
            }
        ]

        self.assertEqual(validate_rubric_payload(rubrics, contract=contract), rubrics)

    def test_validate_rubric_payload_rejects_zero_with_contract(self) -> None:
        contract = RubricContract(
            allowed_dimensions=["Natural Language Fluency"],
            weight_policy=RubricWeightPolicy(
                positive_min=1,
                positive_max=10,
                negative_min=-6,
                negative_max=-1,
                zero_allowed=False,
                integer_only=True,
            ),
            expected_rubric_count=1,
            requires_negative_rubric=False,
            requires_response_specific_when_context_exists=True,
            quality_review_required=True,
        )
        rubrics = [
            {
                "Rubric_dimensions": "Natural Language Fluency",
                "Rubric_title": "Synthetic",
                "Rubrics_description": "Synthetic rubric description for schema validation.",
                "Rubrics_weight": 0,
                "is_response_specific": False,
            }
        ]

        with self.assertRaisesRegex(ValueError, "cannot be zero"):
            validate_rubric_payload(rubrics, contract=contract)


if __name__ == "__main__":
    unittest.main()
