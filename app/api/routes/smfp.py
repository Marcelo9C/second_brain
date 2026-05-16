from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.dependencies import (
    get_smfp_evidence_fusion_service,
    get_smfp_frequency_service,
    get_smfp_health_service,
    get_smfp_inference_service,
    get_smfp_metadata_service,
    get_smfp_ml_service,
    get_smfp_origin_service,
    get_smfp_report_service,
    get_smfp_review_service,
    get_smfp_service,
    get_smfp_snapshot_service,
    get_smfp_timeline_service,
    get_smfp_training_service,
)
from app.schemas.smfp import SmfpAssetCreate, SmfpPublicVerifyRequest, SmfpRevisionCreate
from app.schemas.smfp_evidence_fusion import SmfpEvidenceFusionRequest
from app.schemas.smfp_frequency import SmfpFrequencyAnalyzeRequest
from app.schemas.smfp_inference import SmfpMlInferenceRequest
from app.schemas.smfp_metadata import SmfpMetadataExtractRequest
from app.schemas.smfp_ml import SmfpDatasetSampleCreate, SmfpDatasetSampleUpdate, SmfpMlFeatureExportRequest
from app.schemas.smfp_training import SmfpBaselineTrainRequest, SmfpPromoteRequest
from app.schemas.smfp_review import SmfpReviewCreate
from app.schemas.smfp_snapshot import SmfpSnapshotCreate
from app.schemas.smfp_origin import SmfpOriginAnalyzeRequest
from app.schemas.smfp_report import SmfpReportExportRequest


router = APIRouter(prefix="/api/smfp", tags=["smfp"])


@router.post("/assets")
def ingest_asset(payload: SmfpAssetCreate) -> dict[str, object]:
    return get_smfp_service().ingest_asset(payload)


@router.get("/assets/{asset_id}/manifest")
def get_manifest(asset_id: str) -> dict[str, object]:
    try:
        return get_smfp_service().get_manifest(asset_id)
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.get("/assets/{asset_id}/manifest/export")
def export_manifest(asset_id: str) -> dict[str, object]:
    try:
        manifest = get_smfp_service().get_manifest(asset_id)
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return {
        "asset_id": asset_id,
        "filename": f"{asset_id}.manifest.json",
        "manifest": manifest,
    }


@router.post("/assets/{asset_id}/revisions")
def add_revision(asset_id: str, payload: SmfpRevisionCreate) -> dict[str, object]:
    try:
        return get_smfp_service().add_revision(asset_id, payload)
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.get("/assets/{asset_id}/verify")
def verify_asset(asset_id: str) -> dict[str, object]:
    try:
        return get_smfp_service().verify_asset(asset_id)
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.post("/verify")
def verify_manifest(payload: SmfpPublicVerifyRequest) -> dict[str, object]:
    content = get_smfp_service()._content_bytes(payload.content_base64, payload.content_text)
    return get_smfp_service().verify_manifest_content(manifest=payload.manifest, content=content)


@router.post("/origin/analyze")
def analyze_origin(payload: SmfpOriginAnalyzeRequest) -> dict[str, object]:
    return get_smfp_origin_service().analyze(payload)


@router.post("/metadata/extract")
def extract_metadata(payload: SmfpMetadataExtractRequest) -> dict[str, object]:
    return get_smfp_metadata_service().extract(payload)


@router.post("/frequency/analyze")
def analyze_frequency(payload: SmfpFrequencyAnalyzeRequest) -> dict[str, object]:
    return get_smfp_frequency_service().analyze(payload)


@router.post("/evidence/fuse")
def fuse_evidence(payload: SmfpEvidenceFusionRequest) -> dict[str, object]:
    return get_smfp_evidence_fusion_service().fuse(payload)


@router.post("/reports/export")
def export_report(payload: SmfpReportExportRequest) -> dict[str, object]:
    return get_smfp_report_service().export_json(payload)


@router.post("/ml/features/export")
def export_ml_features(payload: SmfpMlFeatureExportRequest) -> dict[str, object]:
    return get_smfp_ml_service().export_features(payload)


@router.post("/ml/infer")
def infer_ml(payload: SmfpMlInferenceRequest) -> dict[str, object]:
    return get_smfp_inference_service().infer(payload).model_dump()


@router.post("/dataset/samples")
def create_dataset_sample(payload: SmfpDatasetSampleCreate) -> dict[str, object]:
    try:
        return get_smfp_ml_service().create_sample(payload)
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.get("/dataset/samples")
def list_dataset_samples() -> dict[str, object]:
    return get_smfp_ml_service().list_samples()


@router.get("/dataset/summary")
def get_dataset_summary() -> dict[str, object]:
    return get_smfp_ml_service().dataset_summary()


@router.get("/health")
def get_smfp_health() -> dict[str, object]:
    return get_smfp_health_service().check().model_dump()


@router.patch("/dataset/samples/{sample_id}")
def update_dataset_sample(sample_id: str, payload: SmfpDatasetSampleUpdate) -> dict[str, object]:
    try:
        return get_smfp_ml_service().update_sample(sample_id, payload)
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post("/ml/train-baseline")
def train_baseline(payload: SmfpBaselineTrainRequest) -> dict[str, object]:
    try:
        return get_smfp_training_service().train_baseline(payload).model_dump()
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post("/ml/models/{model_id}/promote")
def promote_model(model_id: str, payload: SmfpPromoteRequest) -> dict[str, object]:
    try:
        return get_smfp_training_service().promote_model(model_id, payload).model_dump()
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post("/ml/models/{model_id}/reviews")
def submit_review(model_id: str, payload: SmfpReviewCreate) -> dict[str, object]:
    try:
        return get_smfp_review_service().submit_review(model_id, payload).model_dump()
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.get("/ml/models/{model_id}/reviews")
def list_reviews(model_id: str) -> dict[str, object]:
    try:
        return get_smfp_review_service().list_reviews(model_id).model_dump()
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.post("/ml/models/{model_id}/approve")
def approve_model(model_id: str, payload: SmfpPromoteRequest) -> dict[str, object]:
    try:
        return get_smfp_review_service().approve_promotion(model_id, payload).model_dump()
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.get("/public-keys")
def list_public_keys() -> dict[str, object]:
    return get_smfp_service().list_public_keys()


@router.get("/public-keys/{key_id}")
def get_public_key(key_id: str) -> dict[str, object]:
    try:
        return get_smfp_service().get_public_key(key_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.get("/governance/timeline")
def get_governance_timeline(
    model_id: str | None = None,
    event_type: str | None = None,
) -> dict[str, object]:
    return get_smfp_timeline_service().get_timeline(
        model_id=model_id,
        event_type=event_type,
    ).model_dump()


@router.post("/governance/snapshots")
def create_governance_snapshot(payload: SmfpSnapshotCreate) -> dict[str, object]:
    return get_smfp_snapshot_service().create_snapshot(payload).model_dump()


@router.get("/governance/snapshots")
def list_governance_snapshots() -> dict[str, object]:
    return get_smfp_snapshot_service().list_snapshots().model_dump()


@router.get("/governance/snapshots/compare")
def compare_governance_snapshots(
    a: str,
    b: str,
) -> dict[str, object]:
    try:
        return get_smfp_snapshot_service().compare_snapshots(a, b).model_dump()
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.get("/governance/snapshots/{snapshot_id}")
def get_governance_snapshot(snapshot_id: str) -> dict[str, object]:
    try:
        return get_smfp_snapshot_service().get_snapshot(snapshot_id).model_dump()
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
