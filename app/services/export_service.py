from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from app.repositories.annotations import AnnotationSxSRepository


class AnnotationExportService:
    def __init__(self, *, annotation_repository: AnnotationSxSRepository, export_dir: Path) -> None:
        self.annotation_repository = annotation_repository
        self.export_dir = export_dir

    def export_sft_jsonl(self, *, limit: int = 1000, output_path: str | None = None) -> dict[str, Any]:
        rows = self.annotation_repository.list_for_sft_export(limit=limit)
        self.export_dir.mkdir(parents=True, exist_ok=True)

        if output_path:
            target_path = Path(output_path)
        else:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            target_path = self.export_dir / f"annotations_sft_{timestamp}.jsonl"

        lines: list[str] = []
        for row in rows:
            chosen_output = row["output_a"] if row["chosen"] == "A" else row["output_b"]
            record = {
                "messages": [
                    *(
                        [{"role": "system", "content": row["system_prompt"]}]
                        if row.get("system_prompt")
                        else []
                    ),
                    {"role": "user", "content": row["prompt_original"]},
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
                    "tags": row.get("tags", []),
                },
            }
            lines.append(json.dumps(record, ensure_ascii=False))

        target_path.write_text("\n".join(lines), encoding="utf-8")
        return {
            "path": str(target_path.resolve()),
            "records": len(lines),
        }

    def export_dpo_jsonl(
        self,
        *,
        limit: int = 1000,
        output_path: str | None = None,
        include_metadata: bool = True,
    ) -> dict[str, Any]:
        rows = self.annotation_repository.list_for_sft_export(limit=limit)
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
                    "tags": row.get("tags", []),
                }
            lines.append(json.dumps(record, ensure_ascii=False))

        target_path.write_text("\n".join(lines), encoding="utf-8")
        return {
            "path": str(target_path.resolve()),
            "records": len(lines),
            "skipped": skipped,
            "format": "dpo",
        }

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
