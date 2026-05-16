import json
import tempfile
import unittest
from pathlib import Path

from app.schemas.smfp_actor import SmfpActor
from app.schemas.smfp_snapshot import SmfpSnapshotCreate
from app.services.smfp_snapshot_service import COMPARE_FIELDS, SmfpSnapshotService


class FakeSmfpService:
    signing_key_id = "key-2026-05"
    signing_public_key = "public-key-material-for-tests"

    def _sign(self, payload: dict) -> str:
        return "signed-payload"

    def list_public_keys(self) -> dict:
        return {
            "keys": [
                {
                    "key_id": self.signing_key_id,
                    "public_key": self.signing_public_key,
                    "status": "active",
                    "created_at": "2026-05-15T10:00:00+00:00",
                }
            ]
        }


class FakeTimeline:
    def __init__(self, total_events: int = 1, last_timestamp: str = "2026-05-15T10:00:00+00:00") -> None:
        self.total_events = total_events
        self.last_timestamp = last_timestamp

    def get_timeline(self):
        event = type("TimelineEvent", (), {"timestamp": self.last_timestamp})()
        return type("TimelineResponse", (), {"total_events": self.total_events, "events": [event]})()


class SmfpSnapshotServiceTest(unittest.TestCase):
    def test_snapshot_id_is_derived_from_snapshot_hash_and_excludes_full_public_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = self._service(tmp)

            record = service.create_snapshot(self._create_payload())
            persisted = json.loads((Path(tmp) / "snapshots" / f"{record.snapshot_id}.snapshot.json").read_text())

            self.assertEqual(record.snapshot_id, f"snap_{record.snapshot_hash[:12]}")
            self.assertNotIn("public_key", persisted)
            self.assertEqual(record.key_id, "key-2026-05")
            self.assertTrue(record.public_key_fingerprint)

    def test_compare_snapshots_is_limited_to_governance_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = self._service(tmp)

            first = service.create_snapshot(self._create_payload(notes="before promotion"))
            self._write_model_registry(tmp, active_model="model_b", ml_status="active")
            second = service.create_snapshot(self._create_payload(notes="after promotion"))

            comparison = service.compare_snapshots(first.snapshot_id, second.snapshot_id)

            self.assertEqual([diff["field"] for diff in comparison.diffs], COMPARE_FIELDS)
            self.assertEqual(len(comparison.diffs), 7)
            self.assertGreaterEqual(comparison.total_changed, 1)
            self.assertTrue(
                any(
                    diff["field"] == "active_model" and diff["changed"]
                    for diff in comparison.diffs
                )
            )
            self.assertNotIn("signature", {diff["field"] for diff in comparison.diffs})

    def test_best_effort_snapshot_creation_logs_warning_and_returns_none(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = self._service(tmp)
            service.create_snapshot = lambda payload: (_ for _ in ()).throw(RuntimeError("disk full"))

            with self.assertLogs("app.services.smfp_snapshot_service", level="WARNING") as logs:
                result = service.create_snapshot_best_effort(self._create_payload())

            self.assertIsNone(result)
            self.assertTrue(any("Best-effort governance snapshot failed" in line for line in logs.output))

    def _service(self, tmp: str) -> SmfpSnapshotService:
        self._write_model_registry(tmp)
        self._write_dataset_registry(tmp)
        return SmfpSnapshotService(
            snapshot_dir=Path(tmp) / "snapshots",
            model_registry_path=Path(tmp) / "model_registry.json",
            dataset_registry_path=Path(tmp) / "dataset_registry.json",
            model_dir=Path(tmp) / "models",
            smfp_service=FakeSmfpService(),
            timeline_service=FakeTimeline(),
        )

    def _create_payload(self, notes: str = "manual test snapshot") -> SmfpSnapshotCreate:
        return SmfpSnapshotCreate(
            trigger="manual",
            actor=SmfpActor(actor_type="human", actor_id="analyst", actor_source="test"),
            notes=notes,
        )

    def _write_model_registry(
        self,
        tmp: str,
        *,
        active_model: str | None = "model_a",
        ml_status: str = "active",
    ) -> None:
        Path(tmp, "model_registry.json").write_text(
            json.dumps(
                {
                    "registry_version": "smfp_model_registry_v1",
                    "active_model": active_model,
                    "ml_classifier_status": ml_status,
                    "models": [
                        {"model_id": "model_a", "status": "active"},
                        {"model_id": "model_b", "status": "baseline"},
                    ],
                }
            ),
            encoding="utf-8",
        )

    def _write_dataset_registry(self, tmp: str) -> None:
        Path(tmp, "dataset_registry.json").write_text(
            json.dumps(
                {
                    "registry_version": "smfp_dataset_registry_v1",
                    "samples": [
                        {"sample_id": "s1", "label": "openai_like", "split": "train"},
                        {"sample_id": "s2", "label": "camera_real", "split": "val"},
                        {"sample_id": "s3", "label": None, "split": "unassigned"},
                    ],
                }
            ),
            encoding="utf-8",
        )
