from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.dependencies import (
    get_localization_service,
    get_rubric_generation_service,
    get_rubric_validation_service,
)
from app.schemas.localization import (
    LocalizationCategory,
    RubricCaseCreate,
    RubricCaseExportRequest,
    RubricCaseUpdate,
    RubricGenerateRequest,
    RubricValidationRequest,
)
from app.services.rubric_generation_service import RubricGenerationError


router = APIRouter(prefix="/api/localization", tags=["localization"])


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
    try:
        data = payload.model_dump()
        contract = get_localization_service().active_contract_for_payload(
            data,
            verify_payload_contract=True,
        )
        return get_rubric_generation_service().generate(data, active_contract=contract)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except RubricGenerationError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error


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


@router.get("/providers")
def list_rubric_providers() -> list[dict[str, object]]:
    return get_rubric_generation_service().list_providers()


@router.get("/providers/{provider}/models")
def list_rubric_provider_models(provider: str) -> list[dict[str, object]]:
    try:
        return get_rubric_generation_service().list_models(provider)
    except RubricGenerationError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
