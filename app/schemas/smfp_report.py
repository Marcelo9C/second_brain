from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class SmfpReportExportRequest(BaseModel):
    asset_id: str | None = None
    case_id: str | None = None
    filename: str = ""
    mime_type: str = "application/octet-stream"
    sha256: str | None = None
    timestamp: str | None = None
    provenance_verification: dict[str, Any] = Field(default_factory=dict)
    origin_analysis: dict[str, Any] = Field(default_factory=dict)
    metadata_signals: list[dict[str, Any]] = Field(default_factory=list)
    frequency_signals: list[dict[str, Any]] = Field(default_factory=list)
    evidence_fusion: dict[str, Any] = Field(default_factory=dict)
    limitations: list[str] = Field(default_factory=list)
    analyst_notes: str = ""
    report_version: str = "SMFP v1.6"
    generated_at: str | None = None
    public_verify_base_url: str | None = None


class SmfpReportExportResult(BaseModel):
    report: dict[str, Any]
    canonical_json: str
    report_id: str
    report_hash: str
    report_signature: str
    report_signature_algorithm: str
    report_key_id: str
    public_verify_url: str
    qr_payload: str
    format: str = "json"
    pdf_available: bool = False
