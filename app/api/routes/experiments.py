from fastapi import APIRouter

from app.dependencies import get_experiment_repository, get_retrieval_trace_repository
from app.schemas.experiments import ExperimentCreate


router = APIRouter(prefix="/api/experiments", tags=["experiments"])


@router.get("")
def list_experiments(limit: int = 50) -> list[dict[str, object]]:
    return get_experiment_repository().list_recent(limit=limit)


@router.post("")
def create_experiment(payload: ExperimentCreate) -> dict[str, object]:
    experiment_repo = get_experiment_repository()
    trace_repo = get_retrieval_trace_repository()

    generation = payload.generation.model_dump()
    record = experiment_repo.create(
        {
            "experiment_kind": payload.experiment_kind,
            "title": payload.title,
            "study_label": payload.study_label,
            "status": payload.status,
            "model_name": generation["model_name"],
            "embedding_model": generation.get("embedding_model"),
            "seed": generation["seed"],
            "temperature": generation["temperature"],
            "top_p": generation["top_p"],
            "top_k": generation["top_k"],
            "repeat_penalty": generation.get("repeat_penalty"),
            "max_tokens": generation.get("max_tokens"),
            "chunk_size": generation["chunk_size"],
            "chunk_overlap": generation["chunk_overlap"],
            "corpus_version": generation["corpus_version"],
            "prompt_template_version": generation["prompt_template_version"],
            "retrieval_strategy": generation["retrieval_strategy"],
            "retrieved_top_k": generation["retrieved_top_k"],
            "prompt_messages": payload.prompt_messages,
            "request_payload": payload.request_payload,
            "response_payload": payload.response_payload,
            "metrics": payload.metrics,
            "tags": payload.tags,
            "notes": payload.notes,
        }
    )

    traces = []
    if payload.retrieval_traces:
        trace_rows = []
        for trace in payload.retrieval_traces:
            row = trace.model_dump()
            row["experiment_id"] = record["id"]
            traces.append(row)
            trace_rows.append(row)
        traces = trace_repo.bulk_create(trace_rows)

    return {
        "experiment": record,
        "retrieval_traces": traces,
    }
