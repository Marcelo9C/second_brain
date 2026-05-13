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


def contract_for(
    *,
    allowed_dimensions: list[str],
    negative_min: int,
    expected_rubric_count: int = 1,
) -> RubricContract:
    return RubricContract(
        allowed_dimensions=allowed_dimensions,
        weight_policy=RubricWeightPolicy(
            positive_min=1,
            positive_max=10,
            negative_min=negative_min,
            negative_max=-1,
            zero_allowed=False,
            integer_only=True,
        ),
        expected_rubric_count=expected_rubric_count,
        requires_response_specific_when_context_exists=True,
        quality_review_required=True,
    )


def rubric(*, dimension: str, weight: int | float | str) -> dict:
    return {
        "Rubric_dimensions": dimension,
        "Rubric_title": "Synthetic",
        "Rubrics_description": "Synthetic rubric description for schema validation.",
        "Rubrics_weight": weight,
        "is_response_specific": False,
    }


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
        contract = contract_for(
            allowed_dimensions=["Facts and Local Knowledge"],
            negative_min=-10,
        )
        rubrics = [rubric(dimension="Facts and Local Knowledge", weight=-10)]

        self.assertEqual(validate_rubric_payload(rubrics, contract=contract), rubrics)

    def test_validate_rubric_payload_rejects_zero_with_contract(self) -> None:
        contract = contract_for(
            allowed_dimensions=["Natural Language Fluency"],
            negative_min=-6,
        )
        rubrics = [rubric(dimension="Natural Language Fluency", weight=0)]

        with self.assertRaisesRegex(ValueError, "cannot be zero"):
            validate_rubric_payload(rubrics, contract=contract)

    def test_chitchat_contract_accepts_negative_six_and_rejects_negative_seven(self) -> None:
        contract = contract_for(
            allowed_dimensions=["Natural Language Fluency"],
            negative_min=-6,
        )

        validate_rubric_payload(
            [rubric(dimension="Natural Language Fluency", weight=-6)],
            contract=contract,
        )
        with self.assertRaisesRegex(ValueError, "between -6 and -1"):
            validate_rubric_payload(
                [rubric(dimension="Natural Language Fluency", weight=-7)],
                contract=contract,
            )

    def test_writing_contract_accepts_negative_seven_and_rejects_negative_eight(self) -> None:
        contract = contract_for(
            allowed_dimensions=["Natural Language Fluency"],
            negative_min=-7,
        )

        validate_rubric_payload(
            [rubric(dimension="Natural Language Fluency", weight=-7)],
            contract=contract,
        )
        with self.assertRaisesRegex(ValueError, "between -7 and -1"):
            validate_rubric_payload(
                [rubric(dimension="Natural Language Fluency", weight=-8)],
                contract=contract,
            )

    def test_knowledge_contract_accepts_negative_ten_and_rejects_negative_eleven(self) -> None:
        contract = contract_for(
            allowed_dimensions=["Facts and Local Knowledge"],
            negative_min=-10,
        )

        validate_rubric_payload(
            [rubric(dimension="Facts and Local Knowledge", weight=-10)],
            contract=contract,
        )
        with self.assertRaisesRegex(ValueError, "between -10 and -1"):
            validate_rubric_payload(
                [rubric(dimension="Facts and Local Knowledge", weight=-11)],
                contract=contract,
            )

    def test_knowledge_contract_does_not_depend_on_global_facts_dimension(self) -> None:
        contract = contract_for(
            allowed_dimensions=["Facts and Local Knowledge"],
            negative_min=-10,
        )

        validate_rubric_payload(
            [rubric(dimension="Facts and Local Knowledge", weight=10)],
            contract=contract,
        )
        with self.assertRaisesRegex(ValueError, "invalid Rubric_dimensions"):
            validate_rubric_payload(
                [rubric(dimension="Local Facts and Awareness", weight=10)],
                contract=contract,
            )

    def test_integer_only_contract_rejects_string_and_float_weights(self) -> None:
        contract = contract_for(
            allowed_dimensions=["Natural Language Fluency"],
            negative_min=-6,
        )

        with self.assertRaisesRegex(ValueError, "must be numeric"):
            validate_rubric_payload(
                [rubric(dimension="Natural Language Fluency", weight="-1")],
                contract=contract,
            )
        with self.assertRaisesRegex(ValueError, "must be an integer"):
            validate_rubric_payload(
                [rubric(dimension="Natural Language Fluency", weight=1.5)],
                contract=contract,
            )


if __name__ == "__main__":
    unittest.main()
