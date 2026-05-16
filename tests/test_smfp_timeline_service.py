import json
import tempfile
import unittest
from pathlib import Path

from app.schemas.smfp_review import SmfpReviewCreate
from app.schemas.smfp_training import SmfpBaselineTrainRequest, SmfpPromoteRequest
from app.services.smfp_review_service import SmfpReviewService
from app.services.smfp_timeline_service import SmfpTimelineService
from app.services.smfp_training_service import SmfpTrainingService


class SmfpTimelineServiceTest(unittest.TestCase):
    """Tests for SMFP v2.1 Governance Timeline.

    Verifies that all lifecycle events (sample, training, review, promotion,
    retirement) are aggregated into a chronological audit timeline.
    """

    # ------------------------------------------------------------------
    # Timeline construction
    # ------------------------------------------------------------------

    def test_empty_timeline(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            timeline_svc = self._timeline_service(tmp)
            result = timeline_svc.get_timeline()
            self.assertEqual(result.total_events, 0)
            self.assertEqual(len(result.events), 0)

    def test_dataset_sample_events(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self._write_dataset(tmp, samples=[
                self._sample("a1", "openai_like", "train"),
                self._sample("b1", "camera_real", "train"),
            ])
            timeline_svc = self._timeline_service(tmp)
            result = timeline_svc.get_timeline()

            sample_events = [e for e in result.events if e.event_type == "dataset_sample_added"]
            self.assertEqual(len(sample_events), 2)
            self.assertIsNotNone(sample_events[0].timestamp)
            self.assertIn("a1", sample_events[0].summary)

    def test_baseline_trained_event(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self._train_baseline(tmp)
            timeline_svc = self._timeline_service(tmp)
            result = timeline_svc.get_timeline()

            trained_events = [e for e in result.events if e.event_type == "baseline_trained"]
            self.assertEqual(len(trained_events), 1)
            self.assertIsNotNone(trained_events[0].model_id)
            self.assertIn("trained", trained_events[0].summary)

    def test_review_events(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            training_svc, model_id = self._train_baseline(tmp)
            review_svc = self._review_service(tmp, training_svc)
            review_svc.submit_review(
                model_id,
                SmfpReviewCreate(reviewer_id="marcelo", reviewer_name="Marcelo", decision="approve"),
            )

            timeline_svc = self._timeline_service(tmp)
            result = timeline_svc.get_timeline()

            review_events = [e for e in result.events if e.event_type == "model_approved"]
            self.assertEqual(len(review_events), 1)
            self.assertEqual(review_events[0].model_id, model_id)
            self.assertIn("Marcelo", review_events[0].summary)

    def test_promotion_event(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            training_svc, model_id = self._train_baseline(tmp)
            training_svc.promote_model(model_id, SmfpPromoteRequest())

            timeline_svc = self._timeline_service(tmp)
            result = timeline_svc.get_timeline()

            promoted_events = [e for e in result.events if e.event_type == "model_promoted"]
            self.assertEqual(len(promoted_events), 1)
            self.assertEqual(promoted_events[0].model_id, model_id)
            self.assertIsNotNone(promoted_events[0].actor)
            self.assertEqual(promoted_events[0].actor.actor_type, "human")

    def test_retirement_event(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            training_svc, model_id_1 = self._train_baseline(tmp)
            training_svc.promote_model(model_id_1, SmfpPromoteRequest())

            # Train and promote a second model → first gets retired
            result2 = training_svc.train_baseline(SmfpBaselineTrainRequest())
            model_id_2 = result2.model_id
            training_svc.promote_model(model_id_2, SmfpPromoteRequest())

            timeline_svc = self._timeline_service(tmp)
            result = timeline_svc.get_timeline()

            retired_events = [e for e in result.events if e.event_type == "model_retired"]
            self.assertEqual(len(retired_events), 1)
            self.assertEqual(retired_events[0].model_id, model_id_1)

    # ------------------------------------------------------------------
    # Filtering
    # ------------------------------------------------------------------

    def test_filter_by_model_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            training_svc, model_id = self._train_baseline(tmp)
            timeline_svc = self._timeline_service(tmp)

            result = timeline_svc.get_timeline(model_id=model_id)
            for event in result.events:
                self.assertEqual(event.model_id, model_id)
            self.assertEqual(result.model_id_filter, model_id)

    def test_filter_by_event_type(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self._train_baseline(tmp)
            timeline_svc = self._timeline_service(tmp)

            result = timeline_svc.get_timeline(event_type="baseline_trained")
            for event in result.events:
                self.assertEqual(event.event_type, "baseline_trained")
            self.assertEqual(result.event_type_filter, "baseline_trained")

    # ------------------------------------------------------------------
    # Chronological ordering
    # ------------------------------------------------------------------

    def test_events_are_chronological(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            training_svc, model_id = self._train_baseline(tmp)
            review_svc = self._review_service(tmp, training_svc)
            review_svc.submit_review(
                model_id,
                SmfpReviewCreate(reviewer_id="marcelo", reviewer_name="Marcelo", decision="approve"),
            )
            review_svc.approve_promotion(model_id)

            timeline_svc = self._timeline_service(tmp)
            result = timeline_svc.get_timeline()

            timestamps = [e.timestamp for e in result.events]
            self.assertEqual(timestamps, sorted(timestamps))
            self.assertGreaterEqual(result.total_events, 3)  # samples + trained + review + promoted

    # ------------------------------------------------------------------
    # Full lifecycle
    # ------------------------------------------------------------------

    def test_full_lifecycle_timeline(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            training_svc, model_id = self._train_baseline(tmp)
            review_svc = self._review_service(tmp, training_svc)

            # Review
            review_svc.submit_review(
                model_id,
                SmfpReviewCreate(reviewer_id="analyst", reviewer_name="Analyst", decision="approve"),
            )
            # Approve (promotes via review board)
            review_svc.approve_promotion(model_id)

            timeline_svc = self._timeline_service(tmp)
            result = timeline_svc.get_timeline()

            event_types = [e.event_type for e in result.events]
            self.assertIn("dataset_sample_added", event_types)
            self.assertIn("baseline_trained", event_types)
            self.assertIn("model_approved", event_types)
            self.assertIn("model_promoted", event_types)

            # Verify promoted actor is review_board
            promoted = [e for e in result.events if e.event_type == "model_promoted"][0]
            self.assertEqual(promoted.actor.actor_type, "peer_review")
            self.assertEqual(promoted.actor.actor_id, "review_board")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _timeline_service(self, tmp: str) -> SmfpTimelineService:
        return SmfpTimelineService(
            dataset_registry_path=Path(tmp) / "dataset_registry.json",
            model_registry_path=Path(tmp) / "model_registry.json",
            model_dir=Path(tmp) / "models",
        )

    def _review_service(self, tmp: str, training_svc: SmfpTrainingService) -> SmfpReviewService:
        return SmfpReviewService(
            model_registry_path=Path(tmp) / "model_registry.json",
            model_dir=Path(tmp) / "models",
            training_service=training_svc,
            required_approvals=1,
            governance_profile="lab",
        )

    def _train_baseline(self, tmp: str) -> tuple[SmfpTrainingService, str]:
        self._write_dataset(tmp)
        self._write_registry(tmp)
        svc = SmfpTrainingService(
            dataset_registry_path=Path(tmp) / "dataset_registry.json",
            model_registry_path=Path(tmp) / "model_registry.json",
            model_dir=Path(tmp) / "models",
        )
        result = svc.train_baseline(SmfpBaselineTrainRequest())
        return svc, result.model_id

    def _write_dataset(self, tmp: str, samples: list[dict] | None = None) -> None:
        if samples is None:
            samples = [
                self._sample("a1", "openai_like", "train"),
                self._sample("a2", "openai_like", "train"),
                self._sample("a3", "openai_like", "val"),
                self._sample("b1", "camera_real", "train"),
                self._sample("b2", "camera_real", "train"),
                self._sample("b3", "camera_real", "test"),
            ]
        path = Path(tmp) / "dataset_registry.json"
        if not path.exists():
            path.write_text(json.dumps({
                "registry_version": "smfp_dataset_registry_v1",
                "feature_schema_version": "smfp_features_v1",
                "labels": ["openai_like", "camera_real", "unknown"],
                "samples": samples,
            }), encoding="utf-8")

    def _write_registry(self, tmp: str) -> None:
        path = Path(tmp) / "model_registry.json"
        if not path.exists():
            path.write_text(json.dumps({
                "registry_version": "smfp_model_registry_v1",
                "active_model": None,
                "ml_classifier_status": "disabled",
                "models": [],
            }), encoding="utf-8")

    def _sample(self, prefix: str, label: str, split: str) -> dict:
        return {
            "sample_id": f"smfp_sample_{prefix}",
            "file_hash": prefix * 16,
            "filename": f"{prefix}.png",
            "mime_type": "image/png",
            "label": label,
            "split": split,
            "created_at": f"2026-05-15T10:00:{prefix[1]}0.000000+00:00",
            "updated_at": f"2026-05-15T10:00:{prefix[1]}0.000000+00:00",
            "feature_schema_version": "smfp_features_v1",
            "features": {
                "identity": {"filename": f"{prefix}.png", "content_hash_present": True, "content_hash_prefix": "abc"},
                "metadata_features": {"metadata_signal_count": 2, "metadata_matched_count": 1, "software_tag_count": 1, "creation_tool_hint": "x", "has_exif": "a" not in prefix, "has_xmp": False, "has_pdf_metadata": False, "png_text_chunk_count": 1 if "a" in prefix else 0},
                "origin_heuristic_features": {"likely_producer": label, "origin_confidence_retained_for_audit_only": 0.4, "origin_signal_count": 2, "origin_matched_count": 1, "attribution_level": "heuristic"},
                "frequency_features": {"frequency_signal_count": 1, "frequency_matched_count": 1, "synthetic_likelihood_retained_for_audit_only": 0.6 if "a" in prefix else 0.1, "camera_likelihood_retained_for_audit_only": 0.2 if "a" in prefix else 0.8, "analysis_level": "frequency_heuristic"},
                "dimensions": {"width": 1024, "height": 1024, "aspect_ratio": 1.0},
                "mime_type_features": {"is_image": True, "is_png": True, "is_jpeg": False, "is_pdf": False},
                "compression_hints": {"png_chunk_count": 5, "has_png_text_chunks": "a" in prefix, "jpeg_exif_present": False},
                "provenance_flags": {"has_manifest": True, "content_hash_valid": True, "signature_valid": True, "chain_valid": True, "key_status": "active", "tampering": "none", "signature_algorithm": "Ed25519"},
            },
        }
