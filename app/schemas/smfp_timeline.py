from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.smfp_actor import SmfpActor


# ---------------------------------------------------------------------------
# Event types for the governance timeline
# ---------------------------------------------------------------------------

TimelineEventType = Literal[
    "dataset_sample_added",
    "dataset_sample_labeled",
    "baseline_trained",
    "review_submitted",
    "model_approved",
    "model_promoted",
    "model_retired",
]


class SmfpTimelineEvent(BaseModel):
    """A single immutable event in the model governance timeline."""

    event_type: TimelineEventType
    timestamp: str
    model_id: str | None = None
    sample_id: str | None = None
    review_id: str | None = None
    actor: SmfpActor | None = None
    summary: str = ""
    details: dict = Field(default_factory=dict)


class SmfpTimelineResponse(BaseModel):
    """Chronological governance timeline."""

    total_events: int
    events: list[SmfpTimelineEvent]
    model_id_filter: str | None = None
    event_type_filter: str | None = None
