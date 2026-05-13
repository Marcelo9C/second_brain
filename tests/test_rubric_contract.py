import copy
import json
import unittest
from pathlib import Path

from pydantic import ValidationError

from app.schemas.rubric_contract import TemplateContract, parse_template_contract


ROOT_DIR = Path(__file__).resolve().parents[1]
TEMPLATE_DIR = ROOT_DIR / "Localization" / "pt-br" / "templates"


def load_template(name: str) -> TemplateContract:
    payload = json.loads((TEMPLATE_DIR / name).read_text(encoding="utf-8"))
    return parse_template_contract(payload)


class RubricContractTest(unittest.TestCase):
    def test_chitchat_template_loads_with_contract(self) -> None:
        template = load_template("chitchat_template.json")

        self.assertEqual(template.category, "Chitchat")
        self.assertEqual(template.contract.weight_policy.negative_min, -6)
        self.assertEqual(template.contract.negative_rubric_policy.mode, "recommended")

    def test_writing_template_loads_with_contract(self) -> None:
        template = load_template("writing_template.json")

        self.assertEqual(template.category, "Writing")
        self.assertEqual(template.contract.weight_policy.negative_min, -7)
        self.assertEqual(template.contract.negative_rubric_policy.mode, "recommended")

    def test_knowledge_template_loads_with_contract(self) -> None:
        template = load_template("knowledge_template.json")

        self.assertEqual(template.category, "Knowledge")
        self.assertEqual(template.contract.weight_policy.negative_min, -10)
        self.assertEqual(template.contract.negative_rubric_policy.mode, "recommended")

    def test_expected_rubric_count_matches_slots_for_each_template(self) -> None:
        for path in TEMPLATE_DIR.glob("*.json"):
            with self.subTest(template=path.name):
                template = load_template(path.name)

                self.assertEqual(
                    template.contract.expected_rubric_count,
                    len(template.rubric_slots),
                )

    def test_each_template_weight_passes_own_policy(self) -> None:
        for path in TEMPLATE_DIR.glob("*.json"):
            with self.subTest(template=path.name):
                template = load_template(path.name)
                for rubric in template.rubric_slots:
                    template.contract.weight_policy.validate_weight(rubric["Rubrics_weight"])

    def test_knowledge_accepts_negative_ten_from_own_contract(self) -> None:
        template = load_template("knowledge_template.json")

        template.contract.weight_policy.validate_weight(-10)

    def test_writing_accepts_negative_seven_from_own_contract(self) -> None:
        template = load_template("writing_template.json")

        template.contract.weight_policy.validate_weight(-7)

    def test_chitchat_accepts_negative_six_from_own_contract(self) -> None:
        template = load_template("chitchat_template.json")

        template.contract.weight_policy.validate_weight(-6)

    def test_zero_weight_is_invalid_when_contract_disallows_zero(self) -> None:
        template = load_template("knowledge_template.json")

        with self.assertRaisesRegex(ValueError, "cannot be zero"):
            template.contract.weight_policy.validate_weight(0)

    def test_template_dimensions_must_be_allowed_by_own_contract(self) -> None:
        for path in TEMPLATE_DIR.glob("*.json"):
            with self.subTest(template=path.name):
                template = load_template(path.name)
                allowed = set(template.contract.allowed_dimensions)
                used = {rubric["Rubric_dimensions"] for rubric in template.rubric_slots}

                self.assertTrue(used.issubset(allowed))

    def test_template_without_contract_fails_as_formal_template(self) -> None:
        with self.assertRaisesRegex(ValueError, "must declare a contract"):
            parse_template_contract(
                [
                    {
                        "Rubric_dimensions": "Natural Language Fluency",
                        "Rubric_title": "Synthetic",
                        "Rubrics_description": "Synthetic rubric description.",
                        "Rubrics_weight": 1,
                        "is_response_specific": False,
                    }
                ]
            )

    def test_template_with_weight_outside_own_contract_fails(self) -> None:
        payload = json.loads((TEMPLATE_DIR / "chitchat_template.json").read_text(encoding="utf-8"))
        payload = copy.deepcopy(payload)
        payload["rubric_slots"][0]["Rubrics_weight"] = -7

        with self.assertRaises(ValidationError):
            TemplateContract.model_validate(payload)

    def test_template_with_dimension_outside_own_contract_fails(self) -> None:
        payload = json.loads((TEMPLATE_DIR / "knowledge_template.json").read_text(encoding="utf-8"))
        payload = copy.deepcopy(payload)
        payload["rubric_slots"][0]["Rubric_dimensions"] = "Local Facts and Awareness"

        with self.assertRaises(ValidationError):
            TemplateContract.model_validate(payload)

    def test_recommended_negative_policy_does_not_require_negative_slot(self) -> None:
        payload = json.loads((TEMPLATE_DIR / "chitchat_template.json").read_text(encoding="utf-8"))
        payload = copy.deepcopy(payload)
        payload["contract"]["expected_rubric_count"] = 1
        payload["rubric_slots"] = [
            {
                "Rubric_dimensions": "Natural Language Fluency",
                "Rubric_title": "Positive Only",
                "Rubrics_description": "Synthetic positive-only rubric for contract validation.",
                "Rubrics_weight": 5,
                "is_response_specific": False,
            }
        ]

        template = TemplateContract.model_validate(payload)

        self.assertEqual(template.contract.negative_rubric_policy.mode, "recommended")


if __name__ == "__main__":
    unittest.main()
