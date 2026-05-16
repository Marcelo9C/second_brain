from __future__ import annotations

import base64
import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.schemas.smfp_actor import SmfpActor
from app.schemas.smfp_snapshot import (
    SmfpSnapshotCompareResponse,
    SmfpSnapshotCreate,
    SmfpSnapshotListResponse,
    SmfpSnapshotRecord,
)
from app.services.smfp_json import canonical_json_bytes

logger = logging.getLogger(__name__)

# Fields compared in compare_snapshots — field-level, not raw JSON
COMPARE_FIELDS = [
    "active_model",
    "ml_classifier_status",
    "model_registry_hash",
    "dataset_summary",
    "review_summary",
    "timeline_checkpoint",
    "key_registry_status",
]


class SmfpSnapshotService:
    """Governance snapshot service — append-only, Ed25519-signed.

    Design rules:
    - Snapshots are immutable and never edited after creation.
    - Snapshot ID is content-derived: snap_{snapshot_hash[:12]}.
    - Automatic snapshots are best-effort: failures never rollback
      the triggering operation (e.g. promotion).
    - Only public_key_fingerprint is stored, not the full key.
    """

    def __init__(
        self,
        *,
        snapshot_dir: Path,
        model_registry_path: Path,
        dataset_registry_path: Path,
        model_dir: Path,
        smfp_service: Any,  # SmfpService — for signing + key registry
        timeline_service: Any,  # SmfpTimelineService
    ) -> None:
        self.snapshot_dir = snapshot_dir
        self.model_registry_path = model_registry_path
        self.dataset_registry_path = dataset_registry_path
        self.model_dir = model_dir
        self.smfp_service = smfp_service
        self.timeline_service = timeline_service
        self.snapshot_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def create_snapshot(self, payload: SmfpSnapshotCreate) -> SmfpSnapshotRecord:
        """Freeze current governance state into a signed snapshot."""

        now = datetime.now(timezone.utc).isoformat()

        # 1. Gather frozen state
        model_registry = self._load_json(self.model_registry_path)
        model_registry_hash = self._sha256_of_canonical(model_registry)
        active_model = self._extract_active_model(model_registry)
        ml_status = self._extract_ml_status(model_registry)
        dataset_summary = self._build_dataset_summary()
        review_summary = self._build_review_summary()
        timeline_checkpoint = self._build_timeline_checkpoint()
        key_registry_status = self._build_key_registry_status()

        # 2. Build canonical payload for hashing (excludes signature fields)
        canonical_payload = {
            "timestamp": now,
            "trigger": payload.trigger,
            "actor": payload.actor.model_dump(),
            "notes": payload.notes,
            "active_model": active_model,
            "ml_classifier_status": ml_status,
            "model_registry_hash": model_registry_hash,
            "dataset_summary": dataset_summary,
            "review_summary": review_summary,
            "timeline_checkpoint": timeline_checkpoint,
            "key_registry_status": key_registry_status,
        }

        snapshot_hash = self._sha256_bytes(canonical_json_bytes(canonical_payload))

        # 3. Content-derived ID
        snapshot_id = f"snap_{snapshot_hash[:12]}"

        # 4. Check for duplicate (append-only guard)
        if self._snapshot_path(snapshot_id).exists():
            # Idempotent: return existing record
            return self.get_snapshot(snapshot_id)

        # 5. Sign
        signature = self.smfp_service._sign(canonical_payload)
        key_id = self.smfp_service.signing_key_id
        public_key = self.smfp_service.signing_public_key
        fingerprint = self._sha256_bytes(public_key.encode("utf-8"))[:16]

        # 6. Build record
        record = SmfpSnapshotRecord(
            snapshot_id=snapshot_id,
            timestamp=now,
            trigger=payload.trigger,
            actor=payload.actor,
            notes=payload.notes,
            active_model=active_model,
            ml_classifier_status=ml_status,
            model_registry_hash=model_registry_hash,
            dataset_summary=dataset_summary,
            review_summary=review_summary,
            timeline_checkpoint=timeline_checkpoint,
            key_registry_status=key_registry_status,
            snapshot_hash=snapshot_hash,
            signature=signature,
            signature_algorithm="Ed25519",
            key_id=key_id,
            public_key_fingerprint=fingerprint,
        )

        # 7. Persist (append-only)
        self._write_snapshot(record)

        logger.info(
            "Governance snapshot created: %s (trigger=%s, actor=%s)",
            snapshot_id,
            payload.trigger,
            payload.actor.actor_id,
        )

        return record

    def create_snapshot_best_effort(
        self, payload: SmfpSnapshotCreate
    ) -> SmfpSnapshotRecord | None:
        """Best-effort snapshot creation — never raises.

        Used by auto-triggers (promotion, retirement, incident review).
        If anything fails, logs warning and returns None.
        """
        try:
            return self.create_snapshot(payload)
        except Exception:
            logger.warning(
                "Best-effort governance snapshot failed (trigger=%s, actor=%s)",
                payload.trigger,
                payload.actor.actor_id,
                exc_info=True,
            )
            return None

    def list_snapshots(self) -> SmfpSnapshotListResponse:
        """List all governance snapshots in chronological order."""

        snapshots: list[SmfpSnapshotRecord] = []
        for path in sorted(self.snapshot_dir.glob("*.snapshot.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                snapshots.append(SmfpSnapshotRecord(**data))
            except Exception:
                logger.warning("Skipping invalid snapshot file: %s", path.name)

        snapshots.sort(key=lambda s: s.timestamp)

        return SmfpSnapshotListResponse(
            total_snapshots=len(snapshots),
            snapshots=snapshots,
        )

    def get_snapshot(self, snapshot_id: str) -> SmfpSnapshotRecord:
        """Get a single snapshot by ID."""
        path = self._snapshot_path(snapshot_id)
        if not path.exists():
            raise FileNotFoundError(f"Governance snapshot not found: {snapshot_id}")
        data = json.loads(path.read_text(encoding="utf-8"))
        return SmfpSnapshotRecord(**data)

    def compare_snapshots(
        self, snapshot_id_a: str, snapshot_id_b: str
    ) -> SmfpSnapshotCompareResponse:
        """Field-level comparison of two governance snapshots."""

        snap_a = self.get_snapshot(snapshot_id_a)
        snap_b = self.get_snapshot(snapshot_id_b)

        diffs: list[dict[str, Any]] = []
        changed = 0
        unchanged = 0

        for field in COMPARE_FIELDS:
            val_a = getattr(snap_a, field, None)
            val_b = getattr(snap_b, field, None)
            is_changed = val_a != val_b
            diffs.append({
                "field": field,
                "value_a": val_a,
                "value_b": val_b,
                "changed": is_changed,
            })
            if is_changed:
                changed += 1
            else:
                unchanged += 1

        return SmfpSnapshotCompareResponse(
            snapshot_a=snapshot_id_a,
            snapshot_b=snapshot_id_b,
            timestamp_a=snap_a.timestamp,
            timestamp_b=snap_b.timestamp,
            diffs=diffs,
            total_changed=changed,
            total_unchanged=unchanged,
        )

    # ------------------------------------------------------------------
    # State extraction helpers
    # ------------------------------------------------------------------

    def _extract_active_model(self, registry: dict) -> str | None:
        return registry.get("active_model") or None

    def _extract_ml_status(self, registry: dict) -> str:
        return registry.get("ml_classifier_status", "disabled")

    def _build_dataset_summary(self) -> dict[str, Any]:
        registry = self._load_json(self.dataset_registry_path)
        samples = registry.get("samples", [])
        total = len(samples)
        unlabeled = sum(1 for s in samples if not s.get("label"))
        labels: dict[str, int] = {}
        splits: dict[str, int] = {}
        for s in samples:
            lbl = s.get("label") or "unlabeled"
            labels[lbl] = labels.get(lbl, 0) + 1
            spl = s.get("split") or "unassigned"
            splits[spl] = splits.get(spl, 0) + 1
        return {
            "total_samples": total,
            "unlabeled_count": unlabeled,
            "labeled_count": total - unlabeled,
            "labels": labels,
            "splits": splits,
        }

    def _build_review_summary(self) -> dict[str, Any]:
        total_reviews = 0
        by_model: dict[str, int] = {}
        by_decision: dict[str, int] = {}

        if self.model_dir.exists():
            for review_file in self.model_dir.glob("*_reviews.json"):
                try:
                    data = json.loads(review_file.read_text(encoding="utf-8"))
                    model_id = data.get("model_id", "unknown")
                    reviews = data.get("reviews", [])
                    count = len(reviews)
                    total_reviews += count
                    by_model[model_id] = count
                    for r in reviews:
                        decision = r.get("decision", "unknown")
                        by_decision[decision] = by_decision.get(decision, 0) + 1
                except Exception:
                    continue

        return {
            "total_reviews": total_reviews,
            "by_model": by_model,
            "by_decision": by_decision,
        }

    def _build_timeline_checkpoint(self) -> dict[str, Any]:
        try:
            timeline = self.timeline_service.get_timeline()
            events = timeline.events
            return {
                "total_events": timeline.total_events,
                "last_event_timestamp": events[-1].timestamp if events else None,
            }
        except Exception:
            return {"total_events": 0, "last_event_timestamp": None}

    def _build_key_registry_status(self) -> dict[str, Any]:
        try:
            keys_data = self.smfp_service.list_public_keys()
            keys = keys_data.get("keys", [])
            active = next((k for k in keys if k.get("status") == "active"), None)
            return {
                "total_keys": len(keys),
                "active_key_id": active["key_id"] if active else None,
                "active_key_status": active["status"] if active else "none",
            }
        except Exception:
            return {"total_keys": 0, "active_key_id": None, "active_key_status": "unknown"}

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _snapshot_path(self, snapshot_id: str) -> Path:
        return self.snapshot_dir / f"{snapshot_id}.snapshot.json"

    def _write_snapshot(self, record: SmfpSnapshotRecord) -> None:
        path = self._snapshot_path(record.snapshot_id)
        path.write_text(
            json.dumps(record.model_dump(), ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    # ------------------------------------------------------------------
    # Crypto helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _sha256_bytes(data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    def _sha256_of_canonical(self, obj: dict) -> str:
        return self._sha256_bytes(canonical_json_bytes(obj))

    @staticmethod
    def _load_json(path: Path) -> dict:
        if not path.exists():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))
