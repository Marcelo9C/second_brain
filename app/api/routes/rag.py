from fastapi import APIRouter

from app.dependencies import get_rag_service
from app.schemas.rag import DocumentChunkCreate, RetrieveRequest


router = APIRouter(prefix="/api/rag", tags=["rag"])


@router.post("/chunks")
def ingest_chunks(payload: list[DocumentChunkCreate]) -> dict[str, object]:
    rows = [item.model_dump() for item in payload]
    created = get_rag_service().ingest_chunks(rows)
    return {"chunks": created, "count": len(created)}


@router.post("/retrieve")
def retrieve(payload: RetrieveRequest) -> dict[str, object]:
    rows = get_rag_service().retrieve(**payload.model_dump())
    return {"results": rows, "count": len(rows)}


@router.get("/embedding-models")
def list_embedding_models() -> list[dict[str, object]]:
    return get_rag_service().list_embedding_models()
