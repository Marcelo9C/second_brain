from fastapi import APIRouter

from app.dependencies import get_annotation_export_service, get_annotation_repository
from app.schemas.annotations import AnnotationExportRequest, AnnotationSxSCreate


router = APIRouter(prefix="/api/annotations", tags=["annotations"])


@router.post("/sxs")
def create_annotation(payload: AnnotationSxSCreate) -> dict[str, object]:
    repository = get_annotation_repository()
    record = repository.create(
        {
            "experiment_id": payload.experiment_id,
            "study_label": payload.study_label,
            "annotator": payload.annotator,
            "prompt_original": payload.prompt_original,
            "system_prompt": payload.system_prompt,
            "output_a": payload.output_a,
            "output_b": payload.output_b,
            "candidate_a_label": payload.candidate_a_label,
            "candidate_b_label": payload.candidate_b_label,
            "candidate_a_params": payload.candidate_a_params,
            "candidate_b_params": payload.candidate_b_params,
            "factuality_a": payload.factuality.a,
            "factuality_b": payload.factuality.b,
            "helpfulness_a": payload.helpfulness.a,
            "helpfulness_b": payload.helpfulness.b,
            "grounding_a": payload.grounding.a,
            "grounding_b": payload.grounding.b,
            "chosen": payload.chosen,
            "rejected": payload.rejected,
            "rationale": payload.rationale,
            "metadata": payload.metadata,
            "tags": payload.tags,
        }
    )
    return {"annotation": record}


@router.post("/sxs/export-jsonl")
def export_annotations(payload: AnnotationExportRequest) -> dict[str, object]:
    return get_annotation_export_service().export_sft_jsonl(
        limit=payload.limit,
        output_path=payload.output_path,
    )
