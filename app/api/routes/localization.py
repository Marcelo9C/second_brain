from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from fastapi import APIRouter, HTTPException

from app.dependencies import (
    get_agreement_metrics_service,
    get_candidate_recommendation_service,
    get_localization_service,
    get_rubric_candidate_scoring_service,
    get_rubric_generation_run_repository,
    get_rubric_generation_service,
    get_rubric_validation_service,
)
from app.schemas.localization import (
    CandidateGoldenRecommendationRequest,
    AgreementMetricsRequest,
    LocalizationCategory,
    RubricCandidateScoringRequest,
    RubricCaseCreate,
    RubricCaseExportRequest,
    RubricCaseUpdate,
    RubricGenerateRequest,
    RubricValidationRequest,
)
from app.services.rubric_generation_service import RubricGenerationError


router = APIRouter(prefix="/api/localization", tags=["localization"])
logger = logging.getLogger(__name__)


@router.get("/templates")
def list_templates() -> list[dict[str, object]]:
    return get_localization_service().list_templates()


@router.get("/templates/{locale}/{category}")
def get_template(locale: str, category: LocalizationCategory) -> dict[str, object]:
    try:
        return get_localization_service().get_template(locale=locale, category=category)
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.post("/rubric-cases")
def create_rubric_case(payload: RubricCaseCreate) -> dict[str, object]:
    try:
        record = get_localization_service().create_case(payload.model_dump())
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return {"rubric_case": record}


@router.get("/rubric-cases")
def list_rubric_cases(
    locale: str | None = None,
    category: LocalizationCategory | None = None,
    status: str | None = None,
    limit: int = 100,
) -> list[dict[str, object]]:
    return get_localization_service().list_cases(
        locale=locale,
        category=category,
        status=status,
        limit=limit,
    )


@router.get("/rubric-cases/{case_id}")
def get_rubric_case(case_id: str) -> dict[str, object]:
    record = get_localization_service().get_case(case_id)
    if not record:
        raise HTTPException(status_code=404, detail="Rubric case not found.")
    return record


@router.get("/rubric-cases/{case_id}/runs")
def list_rubric_generation_runs_for_case(case_id: str) -> list[dict[str, object]]:
    record = get_localization_service().get_case(case_id)
    if not record:
        raise HTTPException(status_code=404, detail="Rubric case not found.")
    try:
        return get_rubric_generation_run_repository().list_runs_for_case(case_id)
    except Exception as error:
        logger.debug("Rubric generation runs unavailable for case %s: %s", case_id, error)
        raise HTTPException(
            status_code=503,
            detail=(
                "Rubric run storage is unavailable. Execute "
                "sql/004_rubric_generation_runs.sql before using run history."
            ),
        ) from error


@router.patch("/rubric-cases/{case_id}")
def update_rubric_case(case_id: str, payload: RubricCaseUpdate) -> dict[str, object]:
    updates = payload.model_dump(exclude_unset=True)
    try:
        record = get_localization_service().update_case(case_id, updates)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    if not record:
        raise HTTPException(status_code=404, detail="Rubric case not found.")
    return {"rubric_case": record}


@router.post("/rubric-cases/export-jsonl")
def export_rubric_cases_jsonl(payload: RubricCaseExportRequest) -> dict[str, object]:
    return get_localization_service().export_jsonl(**payload.model_dump())


@router.post("/rubric-cases/export-csv")
def export_rubric_cases_csv(payload: RubricCaseExportRequest) -> dict[str, object]:
    return get_localization_service().export_csv(**payload.model_dump())


@router.post("/rubrics/generate")
def generate_rubrics(payload: RubricGenerateRequest) -> dict[str, object]:
    run_context: dict[str, Any] | None = None
    data: dict[str, Any] = {}
    try:
        data = payload.model_dump()
        localization_service = get_localization_service()
        generation_service = get_rubric_generation_service()
        contract = localization_service.active_contract_for_payload(
            data,
            verify_payload_contract=True,
        )
        run_context = _start_generation_run(data, contract=contract, generation_service=generation_service)
        if not run_context:
            raise HTTPException(
                status_code=503,
                detail=(
                    "Rubric run could not be created. Check PostgreSQL and run "
                    "sql/004_rubric_generation_runs.sql before generating rubrics."
                ),
            )
        result = generation_service.generate(data, active_contract=contract)
        _finish_generation_run(run_context, data, result, contract=contract)
        if run_context and run_context.get("run"):
            result["run_id"] = str(run_context["run"]["id"])
            result["run_number"] = run_context["run"]["run_number"]
            result["case_id"] = str(run_context["run"]["case_id"])
        return result
    except ValueError as error:
        _fail_generation_run(run_context, error, data=data)
        raise HTTPException(status_code=400, detail=str(error)) from error
    except RubricGenerationError as error:
        _fail_generation_run(run_context, error, data=data)
        raise HTTPException(status_code=502, detail=_run_error_detail(run_context, error)) from error


@router.post("/candidate-responses/recommend-golden")
def recommend_golden_candidate(payload: CandidateGoldenRecommendationRequest) -> dict[str, object]:
    try:
        return get_candidate_recommendation_service().recommend(payload.model_dump())
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except RubricGenerationError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error


@router.post("/rubrics/score-candidates")
def score_candidates_with_rubrics(payload: RubricCandidateScoringRequest) -> dict[str, object]:
    data = payload.model_dump()
    try:
        contract = get_localization_service().active_contract_for_payload(
            data,
            verify_payload_contract=True,
        )
        return get_rubric_candidate_scoring_service().score(data, active_contract=contract)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except RubricGenerationError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error


@router.post("/rubrics/agreement-metrics")
def compute_agreement_metrics(payload: AgreementMetricsRequest) -> dict[str, object]:
    try:
        return get_agreement_metrics_service().compute(
            [rating.model_dump() for rating in payload.ratings],
            primary_rater_id=payload.primary_rater_id,
            secondary_rater_id=payload.secondary_rater_id,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post("/rubrics/validate")
def validate_rubrics(payload: RubricValidationRequest) -> dict[str, object]:
    data = payload.model_dump()
    try:
        contract = get_localization_service().active_contract_for_payload(
            data,
            verify_payload_contract=True,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return get_rubric_validation_service().validate_case(data, active_contract=contract)


@router.get("/rubrics/runs/{run_id}")
def get_rubric_generation_run(run_id: str) -> dict[str, object]:
    run = get_rubric_generation_run_repository().get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Rubric generation run not found.")
    return run


@router.post("/rubrics/runs/{run_id}/apply")
def apply_rubric_generation_run(run_id: str) -> dict[str, object]:
    try:
        repository = get_rubric_generation_run_repository()
        run = repository.get_run(run_id)
        if not run:
            raise HTTPException(status_code=404, detail="Rubric generation run not found.")
        if run.get("status") != "success" or not run.get("parsed_rubrics"):
            raise HTTPException(status_code=400, detail="Run cannot be applied.")

        case_id = str(run["case_id"])
        artifact = repository.create_applied_artifact(
            {
                "case_id": case_id,
                "run_id": str(run["id"]),
                "rubrics_snapshot": run["parsed_rubrics"],
                "validation_report": run.get("validation_report"),
                "heuristic_report": run.get("heuristic_report"),
            }
        )

        localization_service = get_localization_service()
        existing = localization_service.get_case(case_id) or {}
        metadata = dict(existing.get("metadata") or {})
        metadata["applied_run_id"] = str(run["id"])
        metadata["applied_artifact_id"] = str(artifact["id"])
        localization_service.update_case(
            case_id,
            {
                "rubrics": run["parsed_rubrics"],
                "metadata": metadata,
            },
        )
        return {
            "artifact_id": str(artifact["id"]),
            "case_id": case_id,
            "run_id": str(run["id"]),
        }
    except HTTPException:
        raise
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.get("/providers")
def list_rubric_providers() -> list[dict[str, object]]:
    return get_rubric_generation_service().list_providers()


@router.get("/providers/{provider}/models")
def list_rubric_provider_models(provider: str) -> list[dict[str, object]]:
    try:
        return get_rubric_generation_service().list_models(provider)
    except RubricGenerationError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


def _start_generation_run(
    data: dict[str, Any],
    *,
    contract: Any,
    generation_service: Any,
) -> dict[str, Any] | None:
    try:
        case_id = data.get("case_id") or _create_draft_case_for_run(data)
        if not case_id:
            return None

        data["case_id"] = str(case_id)
        repository = get_rubric_generation_run_repository()
        run_number = repository.next_run_number(str(case_id))
        prompt_text = generation_service._build_prompt(data, contract=contract).as_text()
        run = repository.create_run(
            {
                "case_id": str(case_id),
                "run_number": run_number,
                "status": "pending",
                "provider_requested": data.get("provider"),
                "model_requested": data.get("model"),
                "model_config": {},
                "input_snapshot": _generation_input_snapshot(data),
                "input_snapshot_hash": _stable_hash(_generation_input_snapshot(data)),
                "prompt_text": prompt_text,
                "approx_prompt_tokens": _approx_tokens(prompt_text),
                "created_by": "system",
            }
        )
        return {"run": run, "repository": repository}
    except Exception as error:
        logger.debug("Rubric generation run persistence unavailable: %s", error)
        return None


def _finish_generation_run(
    run_context: dict[str, Any] | None,
    data: dict[str, Any],
    result: dict[str, Any],
    *,
    contract: Any,
) -> None:
    if not run_context or not run_context.get("run"):
        return

    run = run_context["run"]
    repository = run_context["repository"]
    validation_report = None
    heuristic_report = None
    if result.get("rubrics"):
        validation_payload = {
            **data,
            "rubrics": result.get("rubrics"),
            "metadata": {
                **(data.get("metadata") or {}),
                "human_quality_reviewed": False,
            },
        }
        validation_report = get_rubric_validation_service().validate_case(
            validation_payload,
            active_contract=contract,
        )
        heuristic_report = validation_report.get("qualityHeuristics")

    metadata = result.get("metadata") or {}
    updated_run = repository.update_run(
        str(run["id"]),
        {
            "status": _run_status_from_result(result),
            "provider_used": metadata.get("provider_used"),
            "model_used": metadata.get("model_used"),
            "raw_model_response": result.get("raw_model_response"),
            "parsed_rubrics": result.get("rubrics"),
            "validation_report": validation_report,
            "heuristic_report": heuristic_report,
            "approx_response_tokens": metadata.get("approx_response_tokens"),
            "duration_ms": metadata.get("generation_duration_ms"),
            "response_status": (
                str(metadata.get("response_status"))
                if metadata.get("response_status") is not None
                else None
            ),
            "exact_url_called": metadata.get("exact_url_called"),
            "error_message": result.get("error") or metadata.get("validation_error") or metadata.get("raw_error"),
        },
    )
    _persist_generation_case_snapshot(
        data,
        result,
        run_context={
            **run_context,
            "run": updated_run or run,
        },
        validation_report=validation_report,
        contract=contract,
    )


def _fail_generation_run(
    run_context: dict[str, Any] | None,
    error: Exception,
    *,
    data: dict[str, Any] | None = None,
) -> None:
    if not run_context or not run_context.get("run"):
        return
    try:
        updated_run = run_context["repository"].update_run(
            str(run_context["run"]["id"]),
            {
                "status": "failed",
                "error_message": str(error),
            },
        )
        _persist_generation_case_snapshot(
            data or {},
            {
                "success": False,
                "rubrics": None,
                "metadata": {
                    "generation_failure_type": "provider_failed",
                    "validation_status": "failed",
                    "raw_error": str(error),
                },
                "raw_model_response": None,
                "error": str(error),
            },
            run_context={
                **run_context,
                "run": updated_run or run_context["run"],
            },
            validation_report=None,
            contract=None,
        )
    except Exception as persistence_error:
        logger.debug("Could not mark rubric generation run as failed: %s", persistence_error)


def _persist_generation_case_snapshot(
    data: dict[str, Any],
    result: dict[str, Any],
    *,
    run_context: dict[str, Any] | None,
    validation_report: dict[str, Any] | None,
    contract: Any,
) -> None:
    if not run_context or not run_context.get("run"):
        return

    run = run_context["run"]
    case_id = str(run.get("case_id") or data.get("case_id") or "")
    if not case_id:
        return

    try:
        localization_service = get_localization_service()
        existing = localization_service.get_case(case_id) or {}
        existing_metadata = existing.get("metadata") if isinstance(existing.get("metadata"), dict) else {}
        request_metadata = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
        generation_metadata = {
            **(result.get("metadata") or {}),
            "run_id": str(run.get("id")),
            "run_number": run.get("run_number"),
            "case_id": case_id,
            "category": data.get("category") or existing.get("category"),
            "locale": data.get("locale") or existing.get("locale"),
            "template_contract": data.get("contract"),
        }
        metadata = {
            **existing_metadata,
            **request_metadata,
            "source": "localization_rubric_lab",
            "created_for_generation_run": existing_metadata.get(
                "created_for_generation_run",
                request_metadata.get("created_for_generation_run", False),
            ),
            "rubric_generation": generation_metadata,
            "raw_model_response": result.get("raw_model_response"),
        }
        if validation_report is not None:
            metadata["validation_report"] = validation_report

        updates: dict[str, Any] = {
            "locale": data.get("locale") or existing.get("locale") or "pt-BR",
            "category": data.get("category") or existing.get("category"),
            "chat_history": data.get("chat_history") if data.get("chat_history") is not None else existing.get("chat_history", []),
            "prompt": data.get("prompt") if data.get("prompt") is not None else existing.get("prompt"),
            "response_raw": data.get("response_raw") if data.get("response_raw") is not None else existing.get("response_raw"),
            "golden_response": data.get("golden_response")
            if data.get("golden_response") is not None
            else existing.get("golden_response"),
            "metadata": metadata,
        }
        if result.get("success") is True and result.get("rubrics"):
            updates["rubrics"] = result.get("rubrics")
            updates["status"] = "draft"

        localization_service.update_case(case_id, updates)
    except Exception as error:
        logger.debug("Could not persist rubric generation snapshot for case %s: %s", case_id, error)


def _run_error_detail(run_context: dict[str, Any] | None, error: Exception) -> dict[str, Any]:
    detail: dict[str, Any] = {"message": str(error)}
    if run_context and run_context.get("run"):
        run = run_context["run"]
        detail.update(
            {
                "run_id": str(run.get("id")),
                "run_number": run.get("run_number"),
                "case_id": str(run.get("case_id")),
            }
        )
    return detail


def _create_draft_case_for_run(data: dict[str, Any]) -> str | None:
    try:
        localization_service = get_localization_service()
        template_name = localization_service.category_templates.get(
            str(data.get("category")),
            f"{str(data.get('category') or 'base').lower()}_template.json",
        )
        record = localization_service.create_case(
            {
                "locale": data.get("locale") or "pt-BR",
                "category": data.get("category"),
                "chat_history": data.get("chat_history") or [],
                "prompt": data.get("prompt"),
                "response_raw": data.get("response_raw"),
                "golden_response": data.get("golden_response"),
                "evaluator_notes": None,
                "template_name": template_name,
                "template_version": "v1",
                "rubrics": [],
                "status": "draft",
                "tags": [],
                "metadata": {
                    "source": "localization_rubric_lab",
                    "created_for_generation_run": True,
                    "template_contract": data.get("contract"),
                    **(data.get("metadata") or {}),
                },
            }
        )
        return str(record.get("id")) if record.get("id") else None
    except Exception as error:
        logger.debug("Could not create draft case for rubric generation run: %s", error)
        return None


def _run_status_from_result(result: dict[str, Any]) -> str:
    metadata = result.get("metadata") or {}
    if result.get("success") is True:
        return "success"
    if metadata.get("generation_failure_type") == "invalid_rubric_response":
        return "rejected_by_validation"
    if metadata.get("result_discarded") is True or metadata.get("generation_failure_type") == "provider_mismatch_discarded":
        return "discarded"
    return "failed"


def _generation_input_snapshot(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "locale": data.get("locale"),
        "category": data.get("category"),
        "chat_history": data.get("chat_history"),
        "prompt": data.get("prompt"),
        "response_raw": data.get("response_raw"),
        "golden_response": data.get("golden_response"),
        "base_template": data.get("base_template"),
        "contract": data.get("contract"),
        "metadata": data.get("metadata") or {},
        "candidate_responses": data.get("candidate_responses"),
        "selected_candidate_id": data.get("selected_candidate_id"),
    }


def _stable_hash(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _approx_tokens(value: str | None) -> int:
    if not value:
        return 0
    return max(1, round(len(value) / 4))
