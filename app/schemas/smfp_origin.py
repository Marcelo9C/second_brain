from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


SmfpLikelyProducer = Literal[
    "openai_like",
    "midjourney_like",
    "flux_like",
    "stable_diffusion_like",
    "gemini_like",
    "sora_like",
    "unknown",
]


class SmfpOriginAnalyzeRequest(BaseModel):
    filename: str = ""
    mime_type: str = "application/octet-stream"
    content_hash: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    manifest: dict[str, Any] | None = None
    content_base64: str | None = None


class SmfpOriginEvidence(BaseModel):
    type: str
    label: str
    weight: float
    matched: bool


class SmfpOriginAnalysis(BaseModel):
    synthetic_media_likelihood: float = Field(ge=0, le=1)
    likely_producer: SmfpLikelyProducer
    confidence: float = Field(ge=0, le=1)
    evidence: list[SmfpOriginEvidence]
    limitations: list[str]
    attribution_level: Literal["heuristic"] = "heuristic"
