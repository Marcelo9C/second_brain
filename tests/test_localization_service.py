import json
import tempfile
import unittest
from pathlib import Path

from app.services.localization_service import LocalizationService


class StubRepository:
    def create(self, payload: dict) -> dict:
        return payload

    def get_by_id(self, case_id: str) -> dict | None:
        return None

    def update(self, case_id: str, payload: dict) -> dict:
        return payload


def formal_template_payload(*, negative_min: int = -7) -> dict:
    return {
        "template_name": "writing_template.json",
        "template_version": "1.0",
        "locale": "pt-BR",
        "category": "Writing",
        "contract": {
            "allowed_dimensions": ["Natural Language Fluency"],
            "weight_policy": {
                "positive_min": 1,
                "positive_max": 10,
                "negative_min": negative_min,
                "negative_max": -1,
                "zero_allowed": False,
                "integer_only": True,
            },
            "expected_rubric_count": 1,
            "negative_rubric_policy": {
                "mode": "recommended",
            },
            "requires_response_specific_when_context_exists": True,
            "quality_review_required": True,
            "required_fields": [
                "Rubric_dimensions",
                "Rubric_title",
                "Rubrics_description",
                "Rubrics_weight",
                "is_response_specific",
            ],
        },
        "rubric_slots": [
            {
                "Rubric_dimensions": "Natural Language Fluency",
                "Rubric_title": "Synthetic",
                "Rubrics_description": "Synthetic rubric description for service loading.",
                "Rubrics_weight": 1,
                "is_response_specific": False,
            }
        ],
    }


class LocalizationServiceTest(unittest.TestCase):
    def test_template_response_is_marked_as_scaffold(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            localization_dir = Path(directory)
            template_dir = localization_dir / "pt-br" / "templates"
            template_dir.mkdir(parents=True)
            (template_dir / "writing_template.json").write_text(
                json.dumps(formal_template_payload(negative_min=-5)),
                encoding="utf-8",
            )
            service = LocalizationService(
                repository=StubRepository(),
                localization_dir=localization_dir,
            )

            template = service.get_template(locale="pt-BR", category="Writing")

        self.assertEqual(template["artifact_type"], "template_scaffold")
        self.assertFalse(template["rubrics_are_final"])
        self.assertEqual(template["template_version"], "1.0")
        self.assertEqual(template["contract"]["expected_rubric_count"], 1)
        self.assertEqual(template["rubrics"][0]["Rubric_title"], "Synthetic")
        self.assertIn("scaffold", template["message"].lower())

    def test_approved_status_blocks_adulterated_contract_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            localization_dir = Path(directory)
            template_dir = localization_dir / "pt-br" / "templates"
            template_dir.mkdir(parents=True)
            (template_dir / "writing_template.json").write_text(
                json.dumps(formal_template_payload(negative_min=-7)),
                encoding="utf-8",
            )
            service = LocalizationService(
                repository=StubRepository(),
                localization_dir=localization_dir,
            )

            payload = {
                "locale": "pt-BR",
                "category": "Writing",
                "prompt": "Synthetic prompt.",
                "response_raw": "Synthetic response.",
                "golden_response": "Synthetic golden response.",
                "chat_history": [],
                "evaluator_notes": None,
                "template_name": "writing_template.json",
                "template_version": "1.0",
                "rubrics": [
                    {
                        "Rubric_dimensions": "Natural Language Fluency",
                        "Rubric_title": "Invalid relaxed weight",
                        "Rubrics_description": "Synthetic rubric description for approval validation.",
                        "Rubrics_weight": -8,
                        "is_response_specific": False,
                    }
                ],
                "status": "approved",
                "tags": [],
                "metadata": {
                    "human_quality_reviewed": True,
                    "template_contract": formal_template_payload(negative_min=-99)["contract"],
                },
            }

            with self.assertRaisesRegex(ValueError, "contract_mismatch"):
                service.create_case(payload)

    def test_approved_status_saves_formal_contract_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            localization_dir = Path(directory)
            template_dir = localization_dir / "pt-br" / "templates"
            template_dir.mkdir(parents=True)
            (template_dir / "writing_template.json").write_text(
                json.dumps(formal_template_payload(negative_min=-7)),
                encoding="utf-8",
            )
            service = LocalizationService(
                repository=StubRepository(),
                localization_dir=localization_dir,
            )

            record = service.create_case(
                {
                    "locale": "pt-BR",
                    "category": "Writing",
                    "prompt": "Synthetic prompt.",
                    "response_raw": "Synthetic response.",
                    "golden_response": "Synthetic golden response.",
                    "chat_history": [],
                    "evaluator_notes": None,
                    "template_name": "writing_template.json",
                    "template_version": "1.0",
                    "rubrics": [
                        {
                            "Rubric_dimensions": "Natural Language Fluency",
                            "Rubric_title": "Valid formal weight",
                            "Rubrics_description": "Synthetic rubric description for approval validation.",
                            "Rubrics_weight": -7,
                            "is_response_specific": False,
                        }
                    ],
                    "status": "approved",
                    "tags": [],
                    "metadata": {
                        "human_quality_reviewed": True,
                    },
                }
            )

        self.assertEqual(record["metadata"]["template_contract"]["weight_policy"]["negative_min"], -7)

    def test_formal_category_contract_wins_when_template_name_is_unknown(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            localization_dir = Path(directory)
            template_dir = localization_dir / "pt-br" / "templates"
            template_dir.mkdir(parents=True)
            (template_dir / "writing_template.json").write_text(
                json.dumps(formal_template_payload(negative_min=-7)),
                encoding="utf-8",
            )
            service = LocalizationService(
                repository=StubRepository(),
                localization_dir=localization_dir,
            )

            payload = {
                "locale": "pt-BR",
                "category": "Writing",
                "template_name": "unknown_template.json",
                "metadata": {
                    "template_contract": formal_template_payload(negative_min=-99)["contract"],
                },
            }

            with self.assertRaisesRegex(ValueError, "contract_mismatch"):
                service.active_contract_for_payload(payload, verify_payload_contract=True)

    def test_create_case_persists_candidate_responses_in_metadata(self) -> None:
        service = LocalizationService(
            repository=StubRepository(),
            localization_dir=Path("Localization"),
        )

        record = service.create_case(
            {
                "locale": "pt-BR",
                "category": "Writing",
                "prompt": "Synthetic prompt.",
                "response_raw": "Stale legacy response.",
                "golden_response": "Synthetic golden response.",
                "chat_history": [],
                "evaluator_notes": None,
                "template_name": "writing_template.json",
                "template_version": "1.0",
                "rubrics": [],
                "status": "draft",
                "tags": [],
                "metadata": {},
                "candidate_responses": [
                    {"id": "A", "response_raw": "Candidate A response."},
                ],
                "selected_candidate_id": "A",
            }
        )

        self.assertEqual(record["response_raw"], "Candidate A response.")
        self.assertEqual(record["metadata"]["selected_candidate_id"], "A")
        self.assertEqual(record["metadata"]["candidate_responses"][0]["id"], "A")
        self.assertNotIn("candidate_responses", record)
        self.assertNotIn("selected_candidate_id", record)

    def test_candidate_selection_change_after_generation_is_marked_stale(self) -> None:
        service = LocalizationService(
            repository=StubRepository(),
            localization_dir=Path("Localization"),
        )

        record = service.create_case(
            {
                "locale": "pt-BR",
                "category": "Writing",
                "prompt": "Synthetic prompt.",
                "response_raw": None,
                "golden_response": "Synthetic golden response.",
                "chat_history": [],
                "evaluator_notes": None,
                "template_name": "writing_template.json",
                "template_version": "1.0",
                "rubrics": [],
                "status": "draft",
                "tags": [],
                "metadata": {
                    "rubric_generation": {
                        "selected_candidate_id": "A",
                        "validation_status": "valid",
                    },
                    "candidate_responses": [
                        {"id": "A", "response_raw": "Candidate A response."},
                        {"id": "B", "response_raw": "Candidate B response."},
                    ],
                    "selected_candidate_id": "B",
                },
            }
        )

        self.assertEqual(record["response_raw"], "Candidate B response.")
        self.assertTrue(record["metadata"]["rubric_generation"]["stale"])
        self.assertEqual(
            record["metadata"]["rubric_generation"]["stale_reason"],
            "selected_candidate_changed_after_generation",
        )
        self.assertEqual(
            record["metadata"]["rubric_generation"]["generation_state"],
            "stale_generation",
        )
        self.assertEqual(
            record["metadata"]["rubric_generation"]["current_selected_candidate_id"],
            "B",
        )
        self.assertTrue(record["metadata"]["candidate_selection_state"]["stale"])
        self.assertEqual(
            record["metadata"]["candidate_selection_state"]["reason"],
            "selected_candidate_changed_after_generation",
        )


if __name__ == "__main__":
    unittest.main()
