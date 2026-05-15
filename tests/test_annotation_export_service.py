import json
import tempfile
import unittest
from pathlib import Path

from app.services.export_service import AnnotationExportService


class FakeAnnotationRepository:
    def __init__(self, rows):
        self.rows = rows

    def list_for_sft_export(self, limit: int = 1000):
        return self.rows[:limit]


def annotation_row(**overrides):
    row = {
        "id": "00000000-0000-0000-0000-000000000001",
        "experiment_id": None,
        "study_label": "SxS Eval",
        "annotator": "human",
        "prompt_original": "Explain the tradeoff.",
        "system_prompt": "Be concise.",
        "prompt_original_a": None,
        "prompt_original_b": None,
        "system_prompt_a": None,
        "system_prompt_b": None,
        "output_a": "Clear chosen answer.",
        "output_b": "Weak rejected answer.",
        "candidate_a_label": "model-a",
        "candidate_b_label": "model-b",
        "candidate_a_params": {"temperature": 0},
        "candidate_b_params": {"temperature": 0},
        "factuality_a": 5,
        "factuality_b": 3,
        "helpfulness_a": 5,
        "helpfulness_b": 3,
        "grounding_a": 4,
        "grounding_b": 3,
        "chosen": "A",
        "rejected": "B",
        "rationale": "A is clearer.",
        "metadata": {},
        "tags": ["unit"],
    }
    row.update(overrides)
    return row


class AnnotationExportServiceTest(unittest.TestCase):
    def test_export_dpo_jsonl_writes_prompt_chosen_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "dpo.jsonl"
            service = AnnotationExportService(
                annotation_repository=FakeAnnotationRepository([annotation_row()]),
                export_dir=Path(tmp),
            )

            result = service.export_dpo_jsonl(output_path=str(target))

            self.assertEqual(result["records"], 1)
            self.assertEqual(result["skipped"], 0)
            record = json.loads(target.read_text(encoding="utf-8"))
            self.assertEqual(record["prompt"], "System: Be concise.\n\nUser: Explain the tradeoff.")
            self.assertEqual(record["chosen"], "Clear chosen answer.")
            self.assertEqual(record["rejected"], "Weak rejected answer.")
            self.assertEqual(record["metadata"]["chosen_model"], "model-a")
            self.assertEqual(record["metadata"]["rejected_model"], "model-b")

    def test_export_dpo_jsonl_skips_dual_prompt_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "dpo.jsonl"
            service = AnnotationExportService(
                annotation_repository=FakeAnnotationRepository(
                    [
                        annotation_row(
                            prompt_original=None,
                            system_prompt=None,
                            prompt_original_a="Prompt A",
                            prompt_original_b="Prompt B",
                        )
                    ]
                ),
                export_dir=Path(tmp),
            )

            result = service.export_dpo_jsonl(output_path=str(target))

            self.assertEqual(result["records"], 0)
            self.assertEqual(result["skipped"], 1)
            self.assertEqual(target.read_text(encoding="utf-8"), "")


if __name__ == "__main__":
    unittest.main()
