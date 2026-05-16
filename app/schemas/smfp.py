from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class SmfpAssetCreate(BaseModel):
    filename: str = "asset.bin"
    mime_type: str = "application/octet-stream"
    source: str = "api"
    content_base64: str | None = None
    content_text: str | None = None
    created_by: str = "dashem-smfp"
    model: str | None = None
    prompt: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def require_content(self) -> "SmfpAssetCreate":
        if not self.content_base64 and self.content_text is None:
            raise ValueError("content_base64 or content_text is required.")
        return self


class SmfpRevisionCreate(BaseModel):
    content_base64: str | None = None
    content_text: str | None = None
    editor: str = "unknown"
    operation: str = "edit"
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def require_content(self) -> "SmfpRevisionCreate":
        if not self.content_base64 and self.content_text is None:
            raise ValueError("content_base64 or content_text is required.")
        return self


class SmfpPublicVerifyRequest(BaseModel):
    manifest: dict[str, Any]
    content_base64: str | None = None
    content_text: str | None = None

    @model_validator(mode="after")
    def require_content(self) -> "SmfpPublicVerifyRequest":
        if not self.content_base64 and self.content_text is None:
            raise ValueError("content_base64 or content_text is required.")
        return self


class SmfpTrustScore(BaseModel):
    trust_score: int = Field(ge=0, le=100)
    provenance: Literal["verified", "partial", "unverified"]
    signature: Literal["valid", "invalid", "missing"]
    signature_mode: Literal["PUBLIC_ED25519", "LAB_HMAC"]
    signature_algorithm: Literal["Ed25519", "HMAC-SHA256"]
    key_id: str | None = None
    tampering: Literal["none", "suspected", "unknown"]
    ai_probability: float = Field(ge=0, le=1)


class SmfpAuditReport(BaseModel):
    asset_id: str
    chain_valid: bool
    watermark_detected: bool = False
    metadata_removed: bool
    possible_model: str
    confidence: float = Field(ge=0, le=1)
    trust: SmfpTrustScore
