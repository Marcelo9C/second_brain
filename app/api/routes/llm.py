from fastapi import APIRouter

from app.dependencies import get_llm_service
from app.schemas.llm import ChatGenerateRequest


router = APIRouter(prefix="/api/llm", tags=["llm"])


@router.post("/chat")
def generate_chat(payload: ChatGenerateRequest) -> dict[str, object]:
    result = get_llm_service().generate_chat_completion(
        messages=payload.messages,
        generation=payload.generation.model_dump(),
        keep_alive=payload.keep_alive,
    )
    return {"result": result, "metadata": payload.metadata}


@router.get("/models")
def list_models() -> list[dict[str, object]]:
    return get_llm_service().list_models()
