from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class SmfpMetadataExtractRequest(BaseModel):
    filename: str = ""
    mime_type: str = "application/octet-stream"
    content_base64: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class SmfpMetadataSignal(BaseModel):
    type: str
    label: str
    producer_hint: str = "unknown"
    weight: float
    matched: bool


class SmfpMetadataExtraction(BaseModel):
    mime_type: str
    extracted: dict[str, Any]
    signals: list[SmfpMetadataSignal]
    limitations: list[str]
