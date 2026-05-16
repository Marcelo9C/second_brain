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

    def test_export_dpo_jsonl_includes_rubric_scoring_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "dpo.jsonl"
            scoring = {"preference": {"chosen_candidate_id": "A"}, "candidate_scores": []}
            service = AnnotationExportService(
                annotation_repository=FakeAnnotationRepository(
                    [annotation_row(metadata={"rubric_scoring": scoring})]
                ),
                export_dir=Path(tmp),
            )

            service.export_dpo_jsonl(output_path=str(target))

            record = json.loads(target.read_text(encoding="utf-8"))
            self.assertEqual(record["metadata"]["rubric_scoring"], scoring)

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

    def test_export_dpo_jsonl_can_target_single_annotation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "dpo.jsonl"
            service = AnnotationExportService(
                annotation_repository=FakeAnnotationRepository(
                    [
                        annotation_row(id="annotation-old", output_a="Old answer."),
                        annotation_row(id="annotation-current", output_a="Current answer."),
                    ]
                ),
                export_dir=Path(tmp),
            )

            result = service.export_dpo_jsonl(
                output_path=str(target),
                annotation_id="annotation-current",
            )

            self.assertEqual(result["records"], 1)
            record = json.loads(target.read_text(encoding="utf-8"))
            self.assertEqual(record["chosen"], "Current answer.")

    def test_export_sft_jsonl_skips_empty_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "sft.jsonl"
            service = AnnotationExportService(
                annotation_repository=FakeAnnotationRepository(
                    [
                        annotation_row(prompt_original=""),
                        annotation_row(id="valid-row"),
                    ]
                ),
                export_dir=Path(tmp),
            )

            result = service.export_sft_jsonl(output_path=str(target))

            self.assertEqual(result["records"], 1)
            self.assertEqual(result["skipped"], 1)
            self.assertEqual(len(target.read_text(encoding="utf-8").splitlines()), 1)

    def test_export_rm_jsonl_writes_scored_candidate_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "rm.jsonl"
            service = AnnotationExportService(
                annotation_repository=FakeAnnotationRepository(
                    [
                        annotation_row(
                            metadata={
                                "rubric_scoring": {
                                    "rubric_case": {"id": "case-1"},
                                    "preference": {"chosen_candidate_id": "A", "rejected_candidate_id": "B"},
                                    "candidate_scores": [
                                        {
                                            "candidate_id": "A",
                                            "total_score": 12,
                                            "rubric_scores": [{"rubric_index": 1, "points": 10}],
                                        },
                                        {
                                            "candidate_id": "B",
                                            "total_score": -3,
                                            "rubric_scores": [{"rubric_index": 1, "points": -3}],
                                        },
                                    ],
                                }
                            }
                        )
                    ]
                ),
                export_dir=Path(tmp),
            )

            result = service.export_rm_jsonl(output_path=str(target))

            self.assertEqual(result["records"], 2)
            self.assertEqual(result["skipped"], 0)
            records = [json.loads(line) for line in target.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(records[0]["prompt"], "System: Be concise.\n\nUser: Explain the tradeoff.")
            self.assertEqual(records[0]["response"], "Clear chosen answer.")
            self.assertEqual(records[0]["score"], 12)
            self.assertEqual(records[0]["metadata"]["rubric_case"], {"id": "case-1"})
            self.assertEqual(records[1]["candidate"], "B")

    def test_export_rm_jsonl_skips_rows_without_rubric_scoring(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "rm.jsonl"
            service = AnnotationExportService(
                annotation_repository=FakeAnnotationRepository([annotation_row()]),
                export_dir=Path(tmp),
            )

            result = service.export_rm_jsonl(output_path=str(target))

            self.assertEqual(result["records"], 0)
            self.assertEqual(result["skipped"], 1)
            self.assertEqual(target.read_text(encoding="utf-8"), "")


if __name__ == "__main__":
    unittest.main()
