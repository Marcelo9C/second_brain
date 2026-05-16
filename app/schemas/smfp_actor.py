from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class SmfpActor(BaseModel):
    """Structured identity for any actor in the SMFP governance pipeline.

    Designed to support multiple actor types without schema migration:
    - human analyst (manual lab promotion)
    - api (programmatic trigger)
    - ci_cd (automated pipeline)
    - llm_recommendation (AI-assisted suggestion)
    - peer_review (review board consensus)
    """

    actor_type: Literal[
        "human", "api", "ci_cd", "llm_recommendation", "peer_review"
    ] = Field(description="Category of actor performing the action.")
    actor_id: str = Field(
        description="Unique identifier for the actor (e.g. 'marcelo', 'ci-pipeline-01')."
    )
    actor_source: str = Field(
        default="local_lab",
        description="Environment or system origin (e.g. 'local_lab', 'github_actions').",
    )


# ---------------------------------------------------------------------------
# Convenience factories
# ---------------------------------------------------------------------------

def local_human_actor(actor_id: str = "local_operator") -> SmfpActor:
    """Default actor for direct local lab operations."""
    return SmfpActor(actor_type="human", actor_id=actor_id, actor_source="local_lab")


def review_board_actor() -> SmfpActor:
    """Actor used when promotion is triggered via the review board."""
    return SmfpActor(actor_type="peer_review", actor_id="review_board", actor_source="local_lab")
