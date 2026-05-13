from __future__ import annotations

from typing import Any

from app.schemas.localization import ACCEPTED_RUBRIC_DIMENSIONS
from app.services.rubric_quality_heuristic_service import RubricQualityHeuristicService


REQUIRED_RUBRIC_FIELDS = {
    "Rubric_dimensions",
    "Rubric_title",
    "Rubrics_description",
    "Rubrics_weight",
    "is_response_specific",
}


class RubricValidationService:
    def __init__(self, quality_heuristics: RubricQualityHeuristicService | None = None) -> None:
        self.quality_heuristics = quality_heuristics or RubricQualityHeuristicService()

    def validate_case(self, payload: dict[str, Any]) -> dict[str, Any]:
        rubrics = payload.get("rubrics")
        metadata = payload.get("metadata") or {}
        structure = self.structure_validation(rubrics)
        format_result = self.format_validation(rubrics, structure)
        quality_heuristics = self.quality_heuristics.evaluate(payload, structure, format_result)
        quality = self.quality_validation(metadata, structure, format_result)
        approval = self.approval_readiness(payload, structure, format_result, quality)

        return {
            "structureValidation": structure,
            "formatValidation": format_result,
            "qualityHeuristics": quality_heuristics,
            "qualityValidation": quality,
            "approvalReadiness": approval,
        }

    def structure_validation(self, rubrics: Any) -> dict[str, Any]:
        if not isinstance(rubrics, list) or not rubrics:
            return self._result(
                "fail",
                "Rubrics must be a non-empty JSON array.",
                blocking=True,
                count=0,
            )

        issues: list[str] = []
        for index, item in enumerate(rubrics, start=1):
            if not isinstance(item, dict) or isinstance(item, list):
                issues.append(f"Item {index}: must be an object.")
                continue

            missing = sorted(REQUIRED_RUBRIC_FIELDS - set(item.keys()))
            if missing:
                issues.append(f"Item {index}: missing {', '.join(missing)}.")

        if issues:
            return self._result("fail", " ".join(issues), blocking=True, count=len(rubrics))

        return self._result(
            "pass",
            f"{len(rubrics)} rubrics found. Required fields present.",
            count=len(rubrics),
        )

    def format_validation(self, rubrics: Any, structure: dict[str, Any]) -> dict[str, Any]:
        if structure["status"] != "pass":
            return self._result(
                "pending",
                "Format validation pending until structure passes.",
                blocking=True,
                count=structure.get("count", 0),
            )

        issues: list[str] = []
        for index, rubric in enumerate(rubrics, start=1):
            dimension = rubric.get("Rubric_dimensions")
            if not isinstance(dimension, str) or not dimension.strip():
                issues.append(f"Item {index}: Rubric_dimensions must be non-empty text.")
            elif dimension not in ACCEPTED_RUBRIC_DIMENSIONS:
                issues.append(f"Item {index}: Rubric_dimensions is not accepted.")

            title = rubric.get("Rubric_title")
            if not isinstance(title, str) or not title.strip():
                issues.append(f"Item {index}: Rubric_title must be non-empty text.")
            elif len(title.strip()) > 120:
                issues.append(f"Item {index}: Rubric_title should be short and clear.")

            description = rubric.get("Rubrics_description")
            if not isinstance(description, str) or not description.strip():
                issues.append(f"Item {index}: Rubrics_description must be non-empty text.")
            elif len(description.strip()) < 20:
                issues.append(f"Item {index}: Rubrics_description is too short to assess.")

            weight = rubric.get("Rubrics_weight")
            if not isinstance(weight, (int, float)) or isinstance(weight, bool):
                issues.append(f"Item {index}: Rubrics_weight must be numeric.")
            elif weight < -5 or weight > 10 or weight == 0:
                issues.append(f"Item {index}: Rubrics_weight is outside the configured scale.")

            if not isinstance(rubric.get("is_response_specific"), bool):
                issues.append(f"Item {index}: is_response_specific must be true or false.")

        if issues:
            return self._result("fail", " ".join(issues), blocking=True, count=len(rubrics))

        return self._result(
            "pass",
            "Structure and format OK. Quality has not been reviewed.",
            count=len(rubrics),
        )

    def quality_validation(
        self,
        metadata: dict[str, Any],
        structure: dict[str, Any],
        format_result: dict[str, Any],
    ) -> dict[str, Any]:
        if structure["status"] != "pass" or format_result["status"] != "pass":
            return self._result(
                "pending",
                "Quality review pending until structure and format pass.",
                blocking=True,
            )

        if metadata.get("human_quality_reviewed") is True:
            return self._result(
                "pass",
                "Quality review explicitly marked by a human reviewer.",
            )

        return self._result(
            "pending",
            "Quality pending: review atomicity, coverage, weights, relevance, and is_response_specific.",
            blocking=True,
        )

    def approval_readiness(
        self,
        payload: dict[str, Any],
        structure: dict[str, Any],
        format_result: dict[str, Any],
        quality: dict[str, Any],
    ) -> dict[str, Any]:
        missing_case_fields = [
            field
            for field in ("locale", "category", "prompt", "response_raw", "golden_response")
            if not self._has_text(payload.get(field))
        ]
        if missing_case_fields:
            return self._result(
                "blocked",
                f"Approval blocked: missing {', '.join(missing_case_fields)}.",
                blocking=True,
                missing_fields=missing_case_fields,
            )

        for result in (structure, format_result, quality):
            if result["status"] != "pass":
                return self._result(
                    "blocked",
                    "Approval blocked: validation layers are pending or failing.",
                    blocking=True,
                )

        return self._result("pass", "Rubrics ready for approval.")

    def assert_can_use_status(self, payload: dict[str, Any], status: str) -> dict[str, Any]:
        report = self.validate_case(payload)
        if status == "reviewed" and report["qualityValidation"]["status"] != "pass":
            raise ValueError("Status reviewed blocked: quality review is pending or failing.")
        if status == "approved" and report["approvalReadiness"]["status"] != "pass":
            raise ValueError("Status approved blocked: approval readiness is not pass.")
        return report

    def _has_text(self, value: Any) -> bool:
        return isinstance(value, str) and bool(value.strip())

    def _result(
        self,
        status: str,
        message: str,
        *,
        blocking: bool = False,
        **extra: Any,
    ) -> dict[str, Any]:
        return {
            "status": status,
            "message": message,
            "blocking": blocking,
            **extra,
        }
