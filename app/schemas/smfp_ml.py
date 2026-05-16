from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


SmfpMlLabel = Literal[
    "openai_like",
    "midjourney_like",
    "flux_like",
    "stable_diffusion_like",
    "gemini_like",
    "camera_real",
    "unknown",
]


class SmfpMlFeatureExportRequest(BaseModel):
    filename: str = ""
    mime_type: str = "application/octet-stream"
    content_hash: str | None = None
    label: SmfpMlLabel | None = None
    metadata_extraction: dict[str, Any] = Field(default_factory=dict)
    origin_analysis: dict[str, Any] = Field(default_factory=dict)
    frequency_analysis: dict[str, Any] = Field(default_factory=dict)
    provenance_verification: dict[str, Any] = Field(default_factory=dict)
    manifest: dict[str, Any] | None = None


class SmfpMlFeatureExport(BaseModel):
    feature_schema_version: str = "smfp_features_v1"
    features: dict[str, Any]
    label: SmfpMlLabel | None = None
    ml_status: Literal["features_only_no_model"] = "features_only_no_model"
    dataset_registry: dict[str, Any] = Field(default_factory=dict)
    model_registry: dict[str, Any] = Field(default_factory=dict)
    limitations: list[str]


SmfpDatasetSplit = Literal["train", "val", "test", "unassigned"]
SmfpDatasetSource = Literal["manual", "lab", "external"]


class SmfpDatasetSampleCreate(BaseModel):
    file_hash: str
    filename: str = ""
    mime_type: str = "application/octet-stream"
    label: SmfpMlLabel | None = None
    split: SmfpDatasetSplit = "unassigned"
    source: SmfpDatasetSource = "manual"
    license: str = "unknown"
    feature_schema_version: str = "smfp_features_v1"
    features: dict[str, Any] = Field(default_factory=dict)
    analyst_notes: str = ""


class SmfpDatasetSampleUpdate(BaseModel):
    label: SmfpMlLabel | None = None
    split: SmfpDatasetSplit | None = None
    source: SmfpDatasetSource | None = None
    license: str | None = None
    features: dict[str, Any] | None = None
    analyst_notes: str | None = None
