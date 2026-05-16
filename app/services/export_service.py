from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from app.repositories.annotations import AnnotationSxSRepository

logger = logging.getLogger(__name__)


class AnnotationExportService:
    def __init__(self, *, annotation_repository: AnnotationSxSRepository, export_dir: Path) -> None:
        self.annotation_repository = annotation_repository
        self.export_dir = export_dir

    def export_sft_jsonl(
        self,
        *,
        limit: int = 1000,
        output_path: str | None = None,
        annotation_id: str | None = None,
    ) -> dict[str, Any]:
        rows = self._export_rows(limit=limit, annotation_id=annotation_id)
        self.export_dir.mkdir(parents=True, exist_ok=True)

        if output_path:
            target_path = Path(output_path)
        else:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            target_path = self.export_dir / f"annotations_sft_{timestamp}.jsonl"

        lines: list[str] = []
        skipped = 0
        for row in rows:
            prompt = self._shared_prompt(row)
            chosen_key = str(row.get("chosen") or "").upper()
            chosen_output = self._candidate_output(row, chosen_key)
            if not prompt or not chosen_output:
                skipped += 1
                continue
            record = {
                "messages": [
                    {"role": "user", "content": prompt},
                    {"role": "assistant", "content": chosen_output},
                ],
                "metadata": {
                    "annotation_id": str(row["id"]),
                    "experiment_id": str(row["experiment_id"]) if row.get("experiment_id") else None,
                    "study_label": row.get("study_label"),
                    "annotator": row.get("annotator"),
                    "chosen": row.get("chosen"),
                    "rejected": row.get("rejected"),
                    "rationale": row.get("rationale"),
                    "criteria": {
                        "factuality": {"a": row.get("factuality_a"), "b": row.get("factuality_b")},
                        "helpfulness": {"a": row.get("helpfulness_a"), "b": row.get("helpfulness_b")},
                        "grounding": {"a": row.get("grounding_a"), "b": row.get("grounding_b")},
                    },
                    "candidate_a_params": row.get("candidate_a_params", {}),
                    "candidate_b_params": row.get("candidate_b_params", {}),
                    "rubric_scoring": self._metadata(row).get("rubric_scoring"),
                    "tags": row.get("tags", []),
                },
            }
            lines.append(json.dumps(record, ensure_ascii=False))

        target_path.write_text("\n".join(lines), encoding="utf-8")
        logger.info(
            "SxS RM export completed: annotation_id=%s filtered_rows=%s records=%s skipped=%s path=%s",
            annotation_id,
            len(rows),
            len(lines),
            skipped,
            target_path,
        )
        return {
            "path": str(target_path.resolve()),
            "records": len(lines),
            "skipped": skipped,
            "format": "sft",
            "annotation_id": annotation_id,
            "filtered_rows": len(rows),
        }

    def export_dpo_jsonl(
        self,
        *,
        limit: int = 1000,
        output_path: str | None = None,
        include_metadata: bool = True,
        annotation_id: str | None = None,
    ) -> dict[str, Any]:
        rows = self._export_rows(limit=limit, annotation_id=annotation_id)
        self.export_dir.mkdir(parents=True, exist_ok=True)

        if output_path:
            target_path = Path(output_path)
        else:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            target_path = self.export_dir / f"annotations_dpo_{timestamp}.jsonl"

        lines: list[str] = []
        skipped = 0
        for row in rows:
            prompt = self._shared_prompt(row)
            if not prompt:
                skipped += 1
                continue

            chosen_key = str(row.get("chosen") or "").upper()
            rejected_key = str(row.get("rejected") or "").upper()
            chosen_output = self._candidate_output(row, chosen_key)
            rejected_output = self._candidate_output(row, rejected_key)
            if not chosen_output or not rejected_output:
                skipped += 1
                continue

            record: dict[str, Any] = {
                "prompt": prompt,
                "chosen": chosen_output,
                "rejected": rejected_output,
            }
            if include_metadata:
                record["metadata"] = {
                    "annotation_id": str(row["id"]),
                    "experiment_id": str(row["experiment_id"]) if row.get("experiment_id") else None,
                    "source": "sxs",
                    "study_label": row.get("study_label"),
                    "annotator": row.get("annotator"),
                    "chosen": chosen_key,
                    "rejected": rejected_key,
                    "chosen_model": self._candidate_label(row, chosen_key),
                    "rejected_model": self._candidate_label(row, rejected_key),
                    "rationale": row.get("rationale"),
                    "criteria": {
                        "factuality": {"a": row.get("factuality_a"), "b": row.get("factuality_b")},
                        "helpfulness": {"a": row.get("helpfulness_a"), "b": row.get("helpfulness_b")},
                        "grounding": {"a": row.get("grounding_a"), "b": row.get("grounding_b")},
                    },
                    "candidate_a_params": row.get("candidate_a_params", {}),
                    "candidate_b_params": row.get("candidate_b_params", {}),
                    "rubric_scoring": self._metadata(row).get("rubric_scoring"),
                    "tags": row.get("tags", []),
                }
            lines.append(json.dumps(record, ensure_ascii=False))

        target_path.write_text("\n".join(lines), encoding="utf-8")
        logger.info(
            "SxS SFT export completed: annotation_id=%s filtered_rows=%s records=%s skipped=%s path=%s",
            annotation_id,
            len(rows),
            len(lines),
            skipped,
            target_path,
        )
        return {
            "path": str(target_path.resolve()),
            "records": len(lines),
            "skipped": skipped,
            "format": "dpo",
            "annotation_id": annotation_id,
            "filtered_rows": len(rows),
        }

    def export_rm_jsonl(
        self,
        *,
        limit: int = 1000,
        output_path: str | None = None,
        include_metadata: bool = True,
        annotation_id: str | None = None,
    ) -> dict[str, Any]:
        rows = self._export_rows(limit=limit, annotation_id=annotation_id)
        self.export_dir.mkdir(parents=True, exist_ok=True)

        if output_path:
            target_path = Path(output_path)
        else:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            target_path = self.export_dir / f"annotations_rm_{timestamp}.jsonl"

        lines: list[str] = []
        skipped = 0
        for row in rows:
            prompt = self._shared_prompt(row)
            scoring = self._metadata(row).get("rubric_scoring")
            candidate_scores = scoring.get("candidate_scores") if isinstance(scoring, dict) else None
            if not prompt or not isinstance(candidate_scores, list):
                skipped += 1
                continue

            emitted = 0
            for candidate_score in candidate_scores:
                if not isinstance(candidate_score, dict):
                    continue
                candidate_id = str(candidate_score.get("candidate_id") or "").upper()
                response = self._candidate_output(row, candidate_id)
                total_score = candidate_score.get("total_score")
                if not response or not isinstance(total_score, (int, float)):
                    continue

                record: dict[str, Any] = {
                    "prompt": prompt,
                    "response": response,
                    "score": total_score,
                    "candidate": candidate_id,
                }
                if include_metadata:
                    record["metadata"] = {
                        "annotation_id": str(row["id"]),
                        "experiment_id": str(row["experiment_id"]) if row.get("experiment_id") else None,
                        "source": "sxs",
                        "study_label": row.get("study_label"),
                        "annotator": row.get("annotator"),
                        "candidate_model": self._candidate_label(row, candidate_id),
                        "human_chosen": row.get("chosen"),
                        "human_rejected": row.get("rejected"),
                        "judge_preference": scoring.get("preference"),
                        "rubric_case": scoring.get("rubric_case"),
                        "rubric_scores": candidate_score.get("rubric_scores", []),
                        "tags": row.get("tags", []),
                    }
                lines.append(json.dumps(record, ensure_ascii=False))
                emitted += 1

            if emitted == 0:
                skipped += 1

        target_path.write_text("\n".join(lines), encoding="utf-8")
        logger.info(
            "SxS DPO export completed: annotation_id=%s filtered_rows=%s records=%s skipped=%s path=%s",
            annotation_id,
            len(rows),
            len(lines),
            skipped,
            target_path,
        )
        return {
            "path": str(target_path.resolve()),
            "records": len(lines),
            "skipped": skipped,
            "format": "rm",
            "annotation_id": annotation_id,
            "filtered_rows": len(rows),
        }

    def _export_rows(self, *, limit: int, annotation_id: str | None = None) -> list[dict[str, Any]]:
        rows = self.annotation_repository.list_for_sft_export(limit=limit)
        if not annotation_id:
            return rows
        return [row for row in rows if str(row.get("id")) == str(annotation_id)]

    def _shared_prompt(self, row: dict[str, Any]) -> str | None:
        prompt = self._clean_text(row.get("prompt_original"))
        system_prompt = self._clean_text(row.get("system_prompt"))
        if not prompt:
            return None
        if system_prompt:
            return f"System: {system_prompt}\n\nUser: {prompt}"
        return prompt

    def _candidate_output(self, row: dict[str, Any], key: str) -> str | None:
        if key == "A":
            return self._clean_text(row.get("output_a"))
        if key == "B":
            return self._clean_text(row.get("output_b"))
        return None

    def _candidate_label(self, row: dict[str, Any], key: str) -> str | None:
        if key == "A":
            return self._clean_text(row.get("candidate_a_label"))
        if key == "B":
            return self._clean_text(row.get("candidate_b_label"))
        return None

    def _clean_text(self, value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    def _metadata(self, row: dict[str, Any]) -> dict[str, Any]:
        metadata = row.get("metadata")
        return metadata if isinstance(metadata, dict) else {}
