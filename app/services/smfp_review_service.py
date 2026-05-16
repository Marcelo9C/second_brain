from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.schemas.smfp_actor import SmfpActor, review_board_actor
from app.schemas.smfp_review import (
    BLOCKED_STATUSES,
    REVIEWABLE_STATUSES,
    SmfpApproveResponse,
    SmfpReviewCreate,
    SmfpReviewListResponse,
    SmfpReviewRecord,
)
from app.schemas.smfp_training import SmfpPromoteRequest


class SmfpReviewService:
    """Human Review Board for SMFP model governance.

    Design rules:
    - Reviews are append-only (immutable audit trail).
    - Reviews never edit or delete previous records.
    - Post-promotion reviews are allowed (audit-only, no state change).
    - Promotion via review board requires N approvals (configurable).
    - No automatic demotion or retirement from reviews.
    """

    def __init__(
        self,
        *,
        model_registry_path: Path,
        model_dir: Path,
        training_service: Any,  # SmfpTrainingService (avoid circular import)
        required_approvals: int = 1,
        governance_profile: str = "lab",
        snapshot_service: Any | None = None,  # SmfpSnapshotService (optional, for auto-trigger)
    ) -> None:
        self.model_registry_path = model_registry_path
        self.model_dir = model_dir
        self.training_service = training_service
        self.required_approvals = required_approvals
        self.governance_profile = governance_profile
        self.snapshot_service = snapshot_service
        self._logger = logging.getLogger(__name__)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def submit_review(
        self, model_id: str, payload: SmfpReviewCreate
    ) -> SmfpReviewRecord:
        """Submit an immutable review record for a model."""

        # 1. Validate model exists and is reviewable
        model_entry = self._find_model(model_id)
        model_status = model_entry.get("status", "unknown")

        if model_status in BLOCKED_STATUSES:
            raise ValueError(
                f"SMFP review failed: model '{model_id}' has status '{model_status}' "
                f"which does not accept reviews."
            )
        if model_status not in REVIEWABLE_STATUSES:
            raise ValueError(
                f"SMFP review failed: model '{model_id}' has unrecognized status "
                f"'{model_status}'. Reviewable statuses: {sorted(REVIEWABLE_STATUSES)}."
            )

        # 2. Load existing reviews
        reviews = self._load_reviews(model_id)

        # 3. Check for duplicate reviewer (one reviewer = one vote per context)
        for existing in reviews:
            if (
                existing.get("reviewer_id") == payload.reviewer_id
                and existing.get("review_context") == payload.review_context
            ):
                raise ValueError(
                    f"SMFP review failed: reviewer '{payload.reviewer_id}' already "
                    f"submitted a '{payload.review_context}' review for model '{model_id}'."
                )

        # 4. Build immutable record
        now = datetime.now(timezone.utc).isoformat()
        review_id = self._review_id(model_id, payload.reviewer_id, now)

        actor = SmfpActor(
            actor_type="human",
            actor_id=payload.reviewer_id,
            actor_source="local_lab",
        )

        record = SmfpReviewRecord(
            review_id=review_id,
            model_id=model_id,
            reviewer_id=payload.reviewer_id,
            reviewer_name=payload.reviewer_name,
            decision=payload.decision,
            notes=payload.notes,
            review_context=payload.review_context,
            created_at=now,
            actor=actor,
        )

        # 5. Append and persist (append-only)
        reviews.append(record.model_dump())
        self._save_reviews(model_id, reviews)

        # 6. Auto-snapshot on incident review (best-effort)
        if payload.review_context == "incident" and self.snapshot_service:
            self._auto_snapshot_incident(model_id, actor)

        return record

    def list_reviews(self, model_id: str) -> SmfpReviewListResponse:
        """List all reviews for a model with aggregate counts."""

        # Validate model exists
        self._find_model(model_id)

        reviews_raw = self._load_reviews(model_id)
        records = [SmfpReviewRecord(**r) for r in reviews_raw]

        # Count only pre_promotion approvals for promotion eligibility
        pre_promo = [r for r in records if r.review_context == "pre_promotion"]
        approval_count = sum(1 for r in pre_promo if r.decision == "approve")
        rejection_count = sum(1 for r in pre_promo if r.decision == "reject")
        needs_more = sum(1 for r in pre_promo if r.decision == "needs_more_data")

        return SmfpReviewListResponse(
            model_id=model_id,
            reviews=records,
            approval_count=approval_count,
            rejection_count=rejection_count,
            needs_more_data_count=needs_more,
            required_approvals=self.required_approvals,
            promotion_eligible=approval_count >= self.required_approvals and rejection_count == 0,
            governance_profile=self.governance_profile,
        )

    def approve_promotion(
        self, model_id: str, promote_request: SmfpPromoteRequest | None = None
    ) -> SmfpApproveResponse:
        """Attempt promotion via the review board gate.

        Only succeeds if pre_promotion approvals >= required_approvals
        and there are zero rejections.
        """
        if promote_request is None:
            promote_request = SmfpPromoteRequest()

        review_summary = self.list_reviews(model_id)

        # Gate check
        if review_summary.rejection_count > 0:
            return SmfpApproveResponse(
                model_id=model_id,
                promoted=False,
                status="rejected",
                approval_count=review_summary.approval_count,
                required_approvals=self.required_approvals,
                message=(
                    f"Promotion blocked: {review_summary.rejection_count} rejection(s) "
                    f"in pre_promotion reviews. Resolve before promoting."
                ),
            )

        if review_summary.approval_count < self.required_approvals:
            return SmfpApproveResponse(
                model_id=model_id,
                promoted=False,
                status="insufficient_approvals",
                approval_count=review_summary.approval_count,
                required_approvals=self.required_approvals,
                message=(
                    f"Promotion blocked: {review_summary.approval_count} approval(s) "
                    f"of {self.required_approvals} required."
                ),
            )

        # All gates passed — promote via training service with review_board actor
        actor = review_board_actor()
        result = self.training_service.promote_model(
            model_id, promote_request, actor=actor
        )

        return SmfpApproveResponse(
            model_id=model_id,
            promoted=True,
            status="active",
            promoted_at=result.promoted_at,
            promoted_by=actor,
            approval_count=review_summary.approval_count,
            required_approvals=self.required_approvals,
            message=f"Model '{model_id}' promoted to active via review board.",
        )

    # ------------------------------------------------------------------
    # Review persistence (append-only JSON files)
    # ------------------------------------------------------------------

    def _reviews_path(self, model_id: str) -> Path:
        return self.model_dir / f"{model_id}_reviews.json"

    def _load_reviews(self, model_id: str) -> list[dict]:
        path = self._reviews_path(model_id)
        if not path.exists():
            return []
        data = json.loads(path.read_text(encoding="utf-8"))
        return data.get("reviews", [])

    def _save_reviews(self, model_id: str, reviews: list[dict]) -> None:
        path = self._reviews_path(model_id)
        self.model_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "model_id": model_id,
            "review_count": len(reviews),
            "reviews": reviews,
        }
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    # ------------------------------------------------------------------
    # Registry helpers
    # ------------------------------------------------------------------

    def _find_model(self, model_id: str) -> dict:
        registry = self._load_json(self.model_registry_path)
        for entry in registry.get("models", []):
            if entry.get("model_id") == model_id:
                return entry
        raise KeyError(
            f"SMFP review failed: model '{model_id}' not found in model_registry."
        )

    def _load_json(self, path: Path) -> dict:
        if not path.exists():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _auto_snapshot_incident(self, model_id: str, actor: SmfpActor) -> None:
        """Best-effort governance snapshot after incident review."""
        if not self.snapshot_service:
            return
        from app.schemas.smfp_snapshot import SmfpSnapshotCreate

        try:
            self.snapshot_service.create_snapshot_best_effort(
                SmfpSnapshotCreate(
                    trigger="incident_review",
                    actor=actor,
                    notes=f"Auto-snapshot after incident review for model {model_id}.",
                )
            )
        except Exception:
            self._logger.warning(
                "Best-effort governance snapshot failed after incident review for model '%s'.",
                model_id,
                exc_info=True,
            )

    @staticmethod
    def _review_id(model_id: str, reviewer_id: str, timestamp: str) -> str:
        digest = hashlib.sha256(
            f"{model_id}:{reviewer_id}:{timestamp}".encode("utf-8")
        ).hexdigest()[:12]
        return f"review_{digest}"
