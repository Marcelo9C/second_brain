from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from app.schemas.smfp_actor import SmfpActor


# ---------------------------------------------------------------------------
# Snapshot trigger types
# ---------------------------------------------------------------------------

SnapshotTrigger = Literal[
    "manual",
    "promotion",
    "retirement",
    "incident_review",
]


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------

class SmfpSnapshotCreate(BaseModel):
    """Payload to create a governance snapshot."""

    trigger: SnapshotTrigger = Field(
        default="manual",
        description="What caused this snapshot to be created.",
    )
    actor: SmfpActor = Field(
        description="Actor who triggered or requested the snapshot.",
    )
    notes: str = Field(
        default="",
        description="Optional analyst notes for this snapshot.",
    )


class SmfpSnapshotRecord(BaseModel):
    """Immutable, signed governance snapshot record."""

    snapshot_id: str = Field(description="Content-derived ID: snap_{hash[:12]}")
    timestamp: str
    trigger: SnapshotTrigger
    actor: SmfpActor
    notes: str = ""

    # Frozen governance state
    active_model: str | None = None
    ml_classifier_status: str = "disabled"
    model_registry_hash: str = Field(description="SHA-256 of canonical model_registry.json")
    dataset_summary: dict[str, Any] = Field(default_factory=dict)
    review_summary: dict[str, Any] = Field(default_factory=dict)
    timeline_checkpoint: dict[str, Any] = Field(default_factory=dict)
    key_registry_status: dict[str, Any] = Field(default_factory=dict)

    # Cryptographic integrity
    snapshot_hash: str = Field(description="SHA-256 of canonical snapshot payload")
    signature: str = Field(description="Ed25519 base64 signature")
    signature_algorithm: str = "Ed25519"
    key_id: str = ""
    public_key_fingerprint: str = Field(
        default="",
        description="SHA-256 fingerprint of the signing public key (not the full key).",
    )


class SmfpSnapshotListResponse(BaseModel):
    """List of governance snapshots."""

    total_snapshots: int
    snapshots: list[SmfpSnapshotRecord]


class SmfpSnapshotCompareResponse(BaseModel):
    """Field-level diff between two governance snapshots."""

    snapshot_a: str
    snapshot_b: str
    timestamp_a: str
    timestamp_b: str
    diffs: list[dict[str, Any]] = Field(
        default_factory=list,
        description="List of {field, value_a, value_b, changed} dicts.",
    )
    total_changed: int = 0
    total_unchanged: int = 0
