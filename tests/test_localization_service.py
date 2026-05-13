import json
import tempfile
import unittest
from pathlib import Path

from app.services.localization_service import LocalizationService


class StubRepository:
    pass


class LocalizationServiceTest(unittest.TestCase):
    def test_template_response_is_marked_as_scaffold(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            localization_dir = Path(directory)
            template_dir = localization_dir / "pt-br" / "templates"
            template_dir.mkdir(parents=True)
            (template_dir / "writing_template.json").write_text(
                json.dumps(
                    {
                        "template_name": "writing_template.json",
                        "template_version": "1.0",
                        "locale": "pt-BR",
                        "category": "Writing",
                        "contract": {
                            "allowed_dimensions": ["Natural Language Fluency"],
                            "weight_policy": {
                                "positive_min": 1,
                                "positive_max": 10,
                                "negative_min": -5,
                                "negative_max": -1,
                                "zero_allowed": False,
                                "integer_only": True,
                            },
                            "expected_rubric_count": 1,
                            "requires_negative_rubric": False,
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
                ),
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


if __name__ == "__main__":
    unittest.main()
