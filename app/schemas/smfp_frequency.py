from __future__ import annotations

from pydantic import BaseModel, Field


class SmfpFrequencyAnalyzeRequest(BaseModel):
    filename: str = ""
    mime_type: str = "image/png"
    content_base64: str


class SmfpFrequencySignal(BaseModel):
    type: str
    label: str
    value: float
    weight: float
    matched: bool


class SmfpFrequencyAnalysis(BaseModel):
    synthetic_likelihood: float = Field(ge=0, le=1)
    camera_likelihood: float = Field(ge=0, le=1)
    signals: list[SmfpFrequencySignal]
    limitations: list[str]
    analysis_level: str = "frequency_heuristic"
