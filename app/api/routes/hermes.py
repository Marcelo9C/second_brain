from __future__ import annotations

from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException

from app.dependencies import get_hermes_advisor, get_hermes_orchestrator, get_settings
from app.schemas.hermes import HermesRunCreate
from app.schemas.hermes_advise import HermesAdviseRequest, HermesAdviseResponse

router = APIRouter(prefix="/api/hermes", tags=["hermes"])


@router.get("/config")
def get_hermes_config() -> dict[str, str]:
    """Return configured model defaults per role."""
    settings = get_settings()
    return {
        "default_advisor_model": settings.default_advisor_model,
        "default_stress_model": settings.default_stress_model,
        "default_judge_model": settings.default_judge_model,
        "default_scoring_model": settings.default_scoring_model,
        "default_rubric_model": settings.default_rubric_model,
    }


@router.post("/advise")
def advise(payload: HermesAdviseRequest) -> HermesAdviseResponse:
    """Return deterministic Hermes Advisor diagnostics without side effects."""

    return get_hermes_advisor().advise(payload)


@router.post("/run")
async def start_automation_run(
    payload: HermesRunCreate,
    background_tasks: BackgroundTasks,
) -> dict[str, Any]:
    orchestrator = get_hermes_orchestrator()
    try:
        run = orchestrator.create_run(payload.manifest)
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    background_tasks.add_task(
        orchestrator.execute_automation, run.run_id
    )
    return {
        "run_id": run.run_id,
        "status": run.status,
        "persona_count": run.persona_count,
        "message": (
            f"Automação iniciada com {run.persona_count} persona(s). "
            f"Monitore via GET /api/hermes/status/{run.run_id}"
        ),
    }


@router.get("/status/{run_id}")
def get_run_status(run_id: str) -> dict[str, Any]:
    orchestrator = get_hermes_orchestrator()
    run = orchestrator.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Hermes run not found.")
    return run.model_dump()


@router.post("/runs/{run_id}/cancel")
def cancel_run(run_id: str) -> dict[str, Any]:
    orchestrator = get_hermes_orchestrator()
    run = orchestrator.cancel_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Hermes run not found.")
    return run.model_dump()


@router.get("/runs")
def list_runs() -> list[dict[str, Any]]:
    orchestrator = get_hermes_orchestrator()
    return [run.model_dump() for run in orchestrator.list_runs()]
