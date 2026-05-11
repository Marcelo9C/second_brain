from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from app.repositories.localization_repository import LocalizationRubricCaseRepository


class LocalizationService:
    category_templates = {
        "Writing": "writing_template.json",
        "Chitchat": "chitchat_template.json",
        "Knowledge": "knowledge_template.json",
    }

    def __init__(
        self,
        *,
        repository: LocalizationRubricCaseRepository,
        localization_dir: Path,
    ) -> None:
        self.repository = repository
        self.localization_dir = localization_dir

    def list_templates(self) -> list[dict[str, Any]]:
        templates: list[dict[str, Any]] = []
        for locale_dir in sorted(self.localization_dir.iterdir() if self.localization_dir.exists() else []):
            if not locale_dir.is_dir():
                continue
            for category, template_name in self.category_templates.items():
                template_path = locale_dir / "templates" / template_name
                if template_path.exists():
                    templates.append(
                        {
                            "locale": self._display_locale(locale_dir.name),
                            "category": category,
                            "template_name": template_name,
                            "path": str(template_path.relative_to(self.localization_dir.parent)),
                        }
                    )
        return templates

    def get_template(self, *, locale: str, category: str) -> dict[str, Any]:
        template_name = self.category_templates[category]
        template_path = self._locale_dir(locale) / "templates" / template_name
        if not template_path.exists():
            raise FileNotFoundError(f"Template not found: {template_path}")

        rubrics = json.loads(template_path.read_text(encoding="utf-8"))
        return {
            "locale": self._display_locale(locale),
            "category": category,
            "template_name": template_name,
            "template_version": "v1",
            "rubrics": rubrics,
        }

    def create_case(self, payload: dict[str, Any]) -> dict[str, Any]:
        self._assert_can_persist_status(payload)
        return self.repository.create(payload)

    def list_cases(
        self,
        *,
        locale: str | None = None,
        category: str | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        return self.repository.list_recent(
            locale=locale,
            category=category,
            status=status,
            limit=limit,
        )

    def get_case(self, case_id: str) -> dict[str, Any] | None:
        return self.repository.get_by_id(case_id)

    def update_case(self, case_id: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        if payload.get("status") in {"reviewed", "approved"}:
            existing = self.repository.get_by_id(case_id) or {}
            merged_payload = {
                **existing,
                **payload,
                "metadata": payload.get("metadata") if payload.get("metadata") is not None else existing.get("metadata"),
            }
            self._assert_can_persist_status(merged_payload)
        return self.repository.update(case_id, payload)

    def export_jsonl(
        self,
        *,
        locale: str,
        status: str | None = None,
        limit: int = 5000,
        output_path: str | None = None,
    ) -> dict[str, Any]:
        rows = self.list_cases(locale=locale, status=status, limit=limit)
        target_path = self._export_path(locale, "jsonl", output_path)

        lines = [json.dumps(self._export_record(row), ensure_ascii=False, default=str) for row in rows]
        target_path.write_text("\n".join(lines), encoding="utf-8")

        if rows:
            exported_ids = [str(row["id"]) for row in rows]
            for case_id in exported_ids:
                self.repository.update(case_id, {"status": "exported"})

        return {"path": str(target_path.resolve()), "records": len(rows)}

    def export_csv(
        self,
        *,
        locale: str,
        status: str | None = None,
        limit: int = 5000,
        output_path: str | None = None,
    ) -> dict[str, Any]:
        rows = self.list_cases(locale=locale, status=status, limit=limit)
        target_path = self._export_path(locale, "csv", output_path)

        fieldnames = [
            "id",
            "locale",
            "category",
            "status",
            "template_name",
            "template_version",
            "prompt",
            "response_raw",
            "golden_response",
            "evaluator_notes",
            "chat_history",
            "rubrics",
            "tags",
            "metadata",
            "created_at",
            "updated_at",
        ]
        with target_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            for row in rows:
                record = self._export_record(row)
                writer.writerow(
                    {
                        field: (
                            json.dumps(record[field], ensure_ascii=False, default=str)
                            if isinstance(record.get(field), (dict, list))
                            else record.get(field)
                        )
                        for field in fieldnames
                    }
                )

        if rows:
            exported_ids = [str(row["id"]) for row in rows]
            for case_id in exported_ids:
                self.repository.update(case_id, {"status": "exported"})

        return {"path": str(target_path.resolve()), "records": len(rows)}

    def _locale_dir(self, locale: str) -> Path:
        return self.localization_dir / locale.lower()

    def _display_locale(self, locale: str) -> str:
        return "pt-BR" if locale.lower() == "pt-br" else locale

    def _export_path(self, locale: str, extension: str, output_path: str | None) -> Path:
        if output_path:
            target_path = Path(output_path)
        else:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            target_path = (
                self._locale_dir(locale)
                / "exports"
                / f"localization_rubric_cases_{timestamp}.{extension}"
            )
        target_path.parent.mkdir(parents=True, exist_ok=True)
        return target_path

    def _export_record(self, row: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": str(row.get("id")),
            "locale": row.get("locale"),
            "category": row.get("category"),
            "status": row.get("status"),
            "template_name": row.get("template_name"),
            "template_version": row.get("template_version"),
            "prompt": row.get("prompt"),
            "response_raw": row.get("response_raw"),
            "golden_response": row.get("golden_response"),
            "evaluator_notes": row.get("evaluator_notes"),
            "chat_history": row.get("chat_history"),
            "rubrics": row.get("rubrics"),
            "tags": row.get("tags"),
            "metadata": row.get("metadata"),
            "created_at": row.get("created_at"),
            "updated_at": row.get("updated_at"),
        }

    def _assert_can_persist_status(self, payload: dict[str, Any]) -> None:
        status = payload.get("status")
        if status not in {"reviewed", "approved"}:
            return

        generation = (payload.get("metadata") or {}).get("rubric_generation") or {}
        if not generation:
            return

        provider_requested = generation.get("provider_requested")
        provider_used = generation.get("provider_used")
        model_requested = generation.get("model_requested")
        model_used = generation.get("model_used")

        mismatch = bool(generation.get("mismatch"))
        if provider_requested and provider_requested != provider_used:
            mismatch = True
        if model_requested and model_requested != model_used:
            mismatch = True

        if mismatch:
            raise ValueError(
                f"Status {status} bloqueado: modelo/provider usado difere do solicitado."
            )
