from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.schemas.smfp_actor import SmfpActor
from app.schemas.smfp_timeline import (
    SmfpTimelineEvent,
    SmfpTimelineResponse,
)


class SmfpTimelineService:
    """Aggregates governance events from all SMFP data sources into a
    unified chronological timeline.

    Data sources:
    - dataset_registry.json  →  sample_added / sample_labeled events
    - model_registry.json    →  trained / promoted / retired events
    - {model_id}_reviews.json →  review_submitted events
    - {model_id}_metadata.json → training metadata (enrichment)

    Design rules:
    - Read-only service — never mutates source data.
    - Events are reconstructed from existing timestamps.
    - Timeline is always returned in chronological order.
    """

    def __init__(
        self,
        *,
        dataset_registry_path: Path,
        model_registry_path: Path,
        model_dir: Path,
    ) -> None:
        self.dataset_registry_path = dataset_registry_path
        self.model_registry_path = model_registry_path
        self.model_dir = model_dir

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_timeline(
        self,
        *,
        model_id: str | None = None,
        event_type: str | None = None,
    ) -> SmfpTimelineResponse:
        """Build the full governance timeline, optionally filtered."""

        events: list[SmfpTimelineEvent] = []

        # 1. Dataset sample events
        events.extend(self._dataset_events())

        # 2. Model lifecycle events
        events.extend(self._model_events())

        # 3. Review events
        events.extend(self._review_events())

        # 4. Filter
        if model_id:
            events = [e for e in events if e.model_id == model_id]
        if event_type:
            events = [e for e in events if e.event_type == event_type]

        # 5. Sort chronologically
        events.sort(key=lambda e: e.timestamp)

        return SmfpTimelineResponse(
            total_events=len(events),
            events=events,
            model_id_filter=model_id,
            event_type_filter=event_type,
        )

    # ------------------------------------------------------------------
    # Dataset events
    # ------------------------------------------------------------------

    def _dataset_events(self) -> list[SmfpTimelineEvent]:
        registry = self._load_json(self.dataset_registry_path)
        events: list[SmfpTimelineEvent] = []

        for sample in registry.get("samples", []):
            created_at = sample.get("created_at")
            if not created_at:
                continue

            # Sample added
            events.append(SmfpTimelineEvent(
                event_type="dataset_sample_added",
                timestamp=created_at,
                sample_id=sample.get("sample_id"),
                summary=f"Sample '{sample.get('sample_id')}' added ({sample.get('filename', 'unknown')})",
                details={
                    "source": sample.get("source"),
                    "mime_type": sample.get("mime_type"),
                    "split": sample.get("split"),
                },
            ))

            # If labeled, emit a separate labeling event
            label = sample.get("label")
            updated_at = sample.get("updated_at")
            if label and updated_at and updated_at != created_at:
                events.append(SmfpTimelineEvent(
                    event_type="dataset_sample_labeled",
                    timestamp=updated_at,
                    sample_id=sample.get("sample_id"),
                    summary=f"Sample '{sample.get('sample_id')}' labeled as '{label}'",
                    details={"label": label, "split": sample.get("split")},
                ))

        return events

    # ------------------------------------------------------------------
    # Model lifecycle events
    # ------------------------------------------------------------------

    def _model_events(self) -> list[SmfpTimelineEvent]:
        registry = self._load_json(self.model_registry_path)
        events: list[SmfpTimelineEvent] = []

        for model in registry.get("models", []):
            mid = model.get("model_id", "unknown")

            # Trained
            trained_at = model.get("trained_at")
            if trained_at:
                events.append(SmfpTimelineEvent(
                    event_type="baseline_trained",
                    timestamp=trained_at,
                    model_id=mid,
                    summary=f"Model '{mid}' trained ({model.get('algorithm', '?')})",
                    details={
                        "algorithm": model.get("algorithm"),
                        "accuracy": model.get("accuracy"),
                        "macro_f1": model.get("macro_f1"),
                        "labels_used": model.get("labels_used"),
                        "training_samples_used": model.get("training_samples_used"),
                    },
                ))

            # Promoted
            promoted_at = model.get("promoted_at")
            if promoted_at:
                promoted_by = model.get("promoted_by")
                actor = self._parse_actor(promoted_by)
                events.append(SmfpTimelineEvent(
                    event_type="model_promoted",
                    timestamp=promoted_at,
                    model_id=mid,
                    actor=actor,
                    summary=f"Model '{mid}' promoted to active",
                    details={"promoted_by": promoted_by},
                ))

            # Retired
            retired_at = model.get("retired_at")
            if retired_at:
                events.append(SmfpTimelineEvent(
                    event_type="model_retired",
                    timestamp=retired_at,
                    model_id=mid,
                    summary=f"Model '{mid}' retired",
                ))

        return events

    # ------------------------------------------------------------------
    # Review events
    # ------------------------------------------------------------------

    def _review_events(self) -> list[SmfpTimelineEvent]:
        events: list[SmfpTimelineEvent] = []

        if not self.model_dir.exists():
            return events

        for review_file in self.model_dir.glob("*_reviews.json"):
            data = self._load_json(review_file)
            file_model_id = data.get("model_id")

            for review in data.get("reviews", []):
                created_at = review.get("created_at")
                if not created_at:
                    continue

                decision = review.get("decision", "?")
                reviewer = review.get("reviewer_name", review.get("reviewer_id", "unknown"))
                context = review.get("review_context", "pre_promotion")

                # Determine if this is a review or an approval event
                event_type = "review_submitted"
                if decision == "approve" and context == "pre_promotion":
                    # Check if model was actually promoted after this —
                    # we emit model_approved as a distinct event for approve decisions
                    event_type = "model_approved"

                actor_data = review.get("actor")
                actor = SmfpActor(**actor_data) if actor_data else None

                events.append(SmfpTimelineEvent(
                    event_type=event_type,
                    timestamp=created_at,
                    model_id=file_model_id,
                    review_id=review.get("review_id"),
                    actor=actor,
                    summary=f"{reviewer} {decision} ({context})" + (f": {review.get('notes')}" if review.get("notes") else ""),
                    details={
                        "decision": decision,
                        "review_context": context,
                        "reviewer_id": review.get("reviewer_id"),
                    },
                ))

        return events

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _load_json(self, path: Path) -> dict:
        if not path.exists():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))

    @staticmethod
    def _parse_actor(promoted_by: Any) -> SmfpActor | None:
        if isinstance(promoted_by, dict) and "actor_type" in promoted_by:
            return SmfpActor(**promoted_by)
        return None
