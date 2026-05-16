from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


SmfpOverallAssessment = Literal[
    "verified_synthetic_like",
    "verified_unknown",
    "unverified_synthetic_like",
    "tampered",
    "unknown",
]


class SmfpEvidenceFusionRequest(BaseModel):
    provenance: dict[str, Any] = Field(default_factory=dict)
    origin_analysis: dict[str, Any] = Field(default_factory=dict)
    frequency_analysis: dict[str, Any] = Field(default_factory=dict)


class SmfpEvidenceFusionResult(BaseModel):
    overall_assessment: SmfpOverallAssessment
    origin_confidence: float = Field(ge=0, le=1)
    synthetic_likelihood: float = Field(ge=0, le=1)
    evidence_summary: list[str]
    limitations: list[str]
    explainability: list[str]
