from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from app.schemas.smfp_ml import SmfpMlFeatureExportRequest


class SmfpMlInferenceRequest(SmfpMlFeatureExportRequest):
    top_k: int = Field(default=3, ge=1, le=10)


class SmfpMlPrediction(BaseModel):
    label: str
    probability: float


class SmfpMlInferenceResult(BaseModel):
    ml_status: Literal["active", "disabled", "error"]
    model_id: str | None = None
    model_version: str | None = None
    predictions: list[SmfpMlPrediction] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    details: dict[str, Any] = Field(default_factory=dict)
