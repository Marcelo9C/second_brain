from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.smfp_actor import SmfpActor


# ---------------------------------------------------------------------------
# Review context — audit classification
# ---------------------------------------------------------------------------

ReviewContext = Literal[
    "pre_promotion",
    "post_promotion",
    "incident",
    "compliance",
    "drift",
]

# Statuses that accept reviews
REVIEWABLE_STATUSES = frozenset({"baseline", "candidate", "active", "retired"})

# Statuses that block reviews
BLOCKED_STATUSES = frozenset({"revoked", "deleted", "corrupted"})


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------

class SmfpReviewCreate(BaseModel):
    """Payload to submit a review on a model."""

    reviewer_id: str = Field(description="Unique identifier of the reviewer.")
    reviewer_name: str = Field(description="Display name of the reviewer.")
    decision: Literal["approve", "reject", "needs_more_data"] = Field(
        description="Review verdict."
    )
    notes: str = Field(default="", description="Free-form review commentary.")
    review_context: ReviewContext = Field(
        default="pre_promotion",
        description="Context in which the review is being submitted.",
    )


class SmfpReviewRecord(BaseModel):
    """Immutable record of a single review. Never edited after creation."""

    review_id: str
    model_id: str
    reviewer_id: str
    reviewer_name: str
    decision: Literal["approve", "reject", "needs_more_data"]
    notes: str
    review_context: ReviewContext
    created_at: str
    actor: SmfpActor


class SmfpReviewListResponse(BaseModel):
    """Aggregated view of all reviews for a model."""

    model_id: str
    reviews: list[SmfpReviewRecord]
    approval_count: int
    rejection_count: int
    needs_more_data_count: int
    required_approvals: int
    promotion_eligible: bool
    governance_profile: str


class SmfpApproveResponse(BaseModel):
    """Result of attempting promotion via the review board."""

    model_id: str
    promoted: bool
    status: str
    promoted_at: str | None = None
    promoted_by: SmfpActor | None = None
    approval_count: int
    required_approvals: int
    message: str
