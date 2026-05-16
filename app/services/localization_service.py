from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from app.repositories.localization_repository import LocalizationRubricCaseRepository
from app.schemas.localization import normalize_candidate_response_payload
from app.schemas.rubric_contract import RubricContract, parse_template_contract
from app.services.rubric_validation_service import RubricValidationService


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
        validation_service: RubricValidationService | None = None,
    ) -> None:
        self.repository = repository
        self.localization_dir = localization_dir
        self.validation_service = validation_service or RubricValidationService()

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
        template_contract = self.get_template_contract(locale=locale, category=category)
        return {
            "locale": template_contract.locale,
            "category": template_contract.category,
            "template_name": template_contract.template_name,
            "template_version": template_contract.template_version,
            "artifact_type": "template_scaffold",
            "rubrics_are_final": False,
            "message": "Template scaffold loaded. Fill the real case and review before approval.",
            "contract": template_contract.contract.model_dump(mode="json"),
            "rubrics": template_contract.rubric_slots,
        }

    def get_template_contract(
        self,
        *,
        locale: str,
        category: str,
        template_name: str | None = None,
    ):
        template_name = template_name or self.category_templates[category]
        template_path = self._locale_dir(locale) / "templates" / template_name
        if not template_path.exists():
            raise FileNotFoundError(f"Template not found: {template_path}")

        return parse_template_contract(json.loads(template_path.read_text(encoding="utf-8")))

    def active_contract_for_payload(
        self,
        payload: dict[str, Any],
        *,
        verify_payload_contract: bool = False,
    ) -> RubricContract | None:
        contract = self._active_contract_for_payload(payload)
        if verify_payload_contract and contract is not None:
            self._assert_payload_contract_matches(payload, contract)
        return contract

    def formal_template_for_payload(self, payload: dict[str, Any]):
        locale = payload.get("locale")
        category = payload.get("category")
        template_name = payload.get("template_name")
        if not locale or not category:
            return None

        try:
            return self.get_template_contract(
                locale=locale,
                category=category,
                template_name=template_name,
            )
        except FileNotFoundError:
            if template_name:
                return self.get_template_contract(locale=locale, category=category)
            raise

    def create_case(self, payload: dict[str, Any]) -> dict[str, Any]:
        payload = self._normalize_candidate_fields_for_persistence(payload)
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
        incoming_has_metadata = "metadata" in payload
        payload = self._normalize_candidate_fields_for_persistence(payload)
        if payload.get("status") in {"reviewed", "approved"}:
            existing = self.repository.get_by_id(case_id) or {}
            if payload.get("status") == "approved" and existing.get("status") not in {"reviewed", "approved"}:
                raise ValueError("Status approved blocked: mark and save the case as reviewed before approval.")
            if payload.get("status") == "reviewed":
                existing_metadata = existing.get("metadata") if isinstance(existing.get("metadata"), dict) else {}
                payload_metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
                payload["metadata"] = {
                    **existing_metadata,
                    **payload_metadata,
                    "human_quality_reviewed": True,
                }
            elif not incoming_has_metadata:
                payload.pop("metadata", None)
            merged_payload = {
                **existing,
                **payload,
                "metadata": payload.get("metadata") if incoming_has_metadata or payload.get("metadata") is not None else existing.get("metadata"),
            }
            self._assert_can_persist_status(merged_payload)
            payload["metadata"] = merged_payload.get("metadata")
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

        metadata = payload.setdefault("metadata", {})
        client_contract = payload.get("contract") or metadata.get("template_contract")
        if client_contract:
            metadata["client_payload_contract"] = client_contract
        formal_template = self.formal_template_for_payload(payload)
        contract = formal_template.contract if formal_template is not None else None
        if contract is not None:
            metadata["template_contract"] = contract.model_dump(mode="json")
            payload["contract"] = metadata["template_contract"]
        else:
            payload.pop("contract", None)

        report = self.validation_service.assert_can_use_status(
            payload,
            status,
            active_contract=contract,
        )
        metadata["validation_report"] = report

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

    def _active_contract_for_payload(self, payload: dict[str, Any]) -> RubricContract | None:
        locale = payload.get("locale")
        category = payload.get("category")
        template_name = payload.get("template_name")
        if locale and category:
            try:
                return self.get_template_contract(
                    locale=locale,
                    category=category,
                    template_name=template_name,
                ).contract
            except FileNotFoundError:
                if template_name:
                    return self.get_template_contract(locale=locale, category=category).contract

        metadata = payload.get("metadata") or {}
        if metadata.get("template_contract"):
            return RubricContract.model_validate(metadata["template_contract"])
        return None

    def _assert_payload_contract_matches(
        self,
        payload: dict[str, Any],
        formal_contract: RubricContract,
    ) -> None:
        contract_payload = payload.get("contract")
        if not contract_payload:
            contract_payload = (payload.get("metadata") or {}).get("template_contract")
        if not contract_payload:
            return

        provided_contract = RubricContract.model_validate(contract_payload)
        if provided_contract.model_dump(mode="json") != formal_contract.model_dump(mode="json"):
            raise ValueError("contract_mismatch: payload contract differs from formal template contract.")

    def _normalize_candidate_fields_for_persistence(self, payload: dict[str, Any]) -> dict[str, Any]:
        normalized = normalize_candidate_response_payload(payload, require_selection=False)
        metadata = dict(normalized.get("metadata") or {})
        generation = metadata.get("rubric_generation") or {}
        generated_candidate_id = generation.get("selected_candidate_id")
        selected_candidate_id = metadata.get("selected_candidate_id")
        if generated_candidate_id and selected_candidate_id and generated_candidate_id != selected_candidate_id:
            generation = dict(generation)
            generation["stale"] = True
            generation["stale_reason"] = "selected_candidate_changed_after_generation"
            generation["generation_state"] = "stale_generation"
            generation["current_selected_candidate_id"] = selected_candidate_id
            metadata["rubric_generation"] = generation
            metadata["candidate_selection_state"] = {
                "stale": True,
                "reason": "selected_candidate_changed_after_generation",
                "generated_candidate_id": generated_candidate_id,
                "selected_candidate_id": selected_candidate_id,
            }

        normalized["metadata"] = metadata
        normalized.pop("candidate_responses", None)
        normalized.pop("selected_candidate_id", None)
        return normalized
