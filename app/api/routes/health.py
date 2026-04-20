from fastapi import APIRouter

from app.dependencies import get_db, get_llm_service


router = APIRouter(prefix="/api/health", tags=["health"])


@router.get("")
def health_check() -> dict[str, object]:
    db_ok = False
    db_error: str | None = None
    try:
        db_ok = get_db().ping()
    except Exception as error:
        db_error = str(error)

    ollama = get_llm_service().health()
    ollama_ready = bool(ollama.get("ready", False))
    ollama_ok = bool(ollama.get("ok", False))

    return {
        "ok": db_ok and ollama_ok,
        "ready": ollama_ready,
        "database": "reachable" if db_ok else "unreachable",
        "database_error": db_error,
        "ollama": ollama,
        "error": ollama.get("error") or db_error,
    }
