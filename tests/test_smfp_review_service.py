import json
import tempfile
import unittest
from pathlib import Path

from app.schemas.smfp_review import SmfpReviewCreate
from app.schemas.smfp_training import SmfpBaselineTrainRequest, SmfpPromoteRequest
from app.services.smfp_review_service import SmfpReviewService
from app.services.smfp_training_service import SmfpTrainingService


class SmfpReviewServiceTest(unittest.TestCase):
    """Tests for SMFP v2.0 Human Review Board.

    Invariants:
    - Reviews are append-only (immutable audit trail).
    - Post-promotion reviews are audit-only (no state change).
    - Promotion via review board uses actor_type=peer_review.
    - No automatic demotion from reviews.
    """

    # ------------------------------------------------------------------
    # Submit review
    # ------------------------------------------------------------------

    def test_submit_review_creates_record(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            review_svc, model_id = self._setup(tmp)
            record = review_svc.submit_review(
                model_id,
                SmfpReviewCreate(
                    reviewer_id="marcelo",
                    reviewer_name="Marcelo",
                    decision="approve",
                    notes="Looks good",
                    review_context="pre_promotion",
                ),
            )
            self.assertEqual(record.model_id, model_id)
            self.assertEqual(record.decision, "approve")
            self.assertEqual(record.reviewer_id, "marcelo")
            self.assertEqual(record.review_context, "pre_promotion")
            self.assertEqual(record.actor.actor_type, "human")
            self.assertIsNotNone(record.review_id)
            self.assertIsNotNone(record.created_at)

    def test_duplicate_reviewer_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            review_svc, model_id = self._setup(tmp)
            review_svc.submit_review(
                model_id,
                SmfpReviewCreate(
                    reviewer_id="marcelo",
                    reviewer_name="Marcelo",
                    decision="approve",
                ),
            )
            with self.assertRaises(ValueError) as ctx:
                review_svc.submit_review(
                    model_id,
                    SmfpReviewCreate(
                        reviewer_id="marcelo",
                        reviewer_name="Marcelo",
                        decision="reject",
                    ),
                )
            self.assertIn("already submitted", str(ctx.exception))

    def test_same_reviewer_different_context_allowed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            review_svc, model_id = self._setup(tmp)
            review_svc.submit_review(
                model_id,
                SmfpReviewCreate(
                    reviewer_id="marcelo", reviewer_name="Marcelo",
                    decision="approve", review_context="pre_promotion",
                ),
            )
            # Same reviewer, different context → should succeed
            record = review_svc.submit_review(
                model_id,
                SmfpReviewCreate(
                    reviewer_id="marcelo", reviewer_name="Marcelo",
                    decision="approve", review_context="compliance",
                ),
            )
            self.assertEqual(record.review_context, "compliance")

    # ------------------------------------------------------------------
    # List reviews
    # ------------------------------------------------------------------

    def test_list_reviews_returns_all(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            review_svc, model_id = self._setup(tmp)
            review_svc.submit_review(
                model_id,
                SmfpReviewCreate(reviewer_id="a", reviewer_name="A", decision="approve"),
            )
            review_svc.submit_review(
                model_id,
                SmfpReviewCreate(reviewer_id="b", reviewer_name="B", decision="reject"),
            )

            listing = review_svc.list_reviews(model_id)
            self.assertEqual(len(listing.reviews), 2)
            self.assertEqual(listing.approval_count, 1)
            self.assertEqual(listing.rejection_count, 1)
            self.assertFalse(listing.promotion_eligible)
            self.assertEqual(listing.governance_profile, "lab")

    # ------------------------------------------------------------------
    # Approve promotion (review board gate)
    # ------------------------------------------------------------------

    def test_approve_with_sufficient_reviews(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            review_svc, model_id = self._setup(tmp)
            review_svc.submit_review(
                model_id,
                SmfpReviewCreate(reviewer_id="marcelo", reviewer_name="Marcelo", decision="approve"),
            )
            result = review_svc.approve_promotion(model_id)

            self.assertTrue(result.promoted)
            self.assertEqual(result.status, "active")
            self.assertIsNotNone(result.promoted_at)
            self.assertEqual(result.promoted_by.actor_type, "peer_review")
            self.assertEqual(result.promoted_by.actor_id, "review_board")

            registry = self._load_registry(tmp)
            self.assertEqual(registry["active_model"], model_id)
            self.assertEqual(registry["ml_classifier_status"], "active")

    def test_approve_blocked_insufficient_reviews(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            review_svc, model_id = self._setup(tmp)
            # No reviews submitted
            result = review_svc.approve_promotion(model_id)

            self.assertFalse(result.promoted)
            self.assertEqual(result.status, "insufficient_approvals")
            self.assertIn("0 approval(s)", result.message)

    def test_approve_blocked_with_rejection(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            review_svc, model_id = self._setup(tmp)
            review_svc.submit_review(
                model_id,
                SmfpReviewCreate(reviewer_id="a", reviewer_name="A", decision="approve"),
            )
            review_svc.submit_review(
                model_id,
                SmfpReviewCreate(reviewer_id="b", reviewer_name="B", decision="reject"),
            )
            result = review_svc.approve_promotion(model_id)

            self.assertFalse(result.promoted)
            self.assertEqual(result.status, "rejected")
            self.assertIn("rejection", result.message)

    # ------------------------------------------------------------------
    # Model not found
    # ------------------------------------------------------------------

    def test_review_on_nonexistent_model_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            review_svc, _ = self._setup(tmp)
            with self.assertRaises(KeyError):
                review_svc.submit_review(
                    "fake_model",
                    SmfpReviewCreate(reviewer_id="a", reviewer_name="A", decision="approve"),
                )

    # ------------------------------------------------------------------
    # Audit trail immutability
    # ------------------------------------------------------------------

    def test_review_audit_trail_immutable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            review_svc, model_id = self._setup(tmp)
            review_svc.submit_review(
                model_id,
                SmfpReviewCreate(reviewer_id="a", reviewer_name="A", decision="approve"),
            )
            review_svc.submit_review(
                model_id,
                SmfpReviewCreate(reviewer_id="b", reviewer_name="B", decision="reject"),
            )
            # Read raw file — both records must exist, no overwrites
            reviews_path = Path(tmp) / "models" / f"{model_id}_reviews.json"
            raw = json.loads(reviews_path.read_text(encoding="utf-8"))
            self.assertEqual(raw["review_count"], 2)
            self.assertEqual(len(raw["reviews"]), 2)
            ids = [r["review_id"] for r in raw["reviews"]]
            self.assertEqual(len(set(ids)), 2)  # unique IDs

    # ------------------------------------------------------------------
    # Actor model via review board
    # ------------------------------------------------------------------

    def test_promoted_by_is_actor_object(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            review_svc, model_id = self._setup(tmp)
            review_svc.submit_review(
                model_id,
                SmfpReviewCreate(reviewer_id="marcelo", reviewer_name="Marcelo", decision="approve"),
            )
            review_svc.approve_promotion(model_id)

            registry = self._load_registry(tmp)
            model_entry = next(m for m in registry["models"] if m["model_id"] == model_id)
            promoted_by = model_entry["promoted_by"]
            self.assertIsInstance(promoted_by, dict)
            self.assertEqual(promoted_by["actor_type"], "peer_review")
            self.assertEqual(promoted_by["actor_id"], "review_board")
            self.assertEqual(promoted_by["actor_source"], "local_lab")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _setup(self, tmp: str) -> tuple[SmfpReviewService, str]:
        """Train a baseline model and return (review_service, model_id)."""
        samples = [
            self._sample("a1", "openai_like", "train"),
            self._sample("a2", "openai_like", "train"),
            self._sample("a3", "openai_like", "val"),
            self._sample("b1", "camera_real", "train"),
            self._sample("b2", "camera_real", "train"),
            self._sample("b3", "camera_real", "test"),
        ]
        dataset_path = Path(tmp) / "dataset_registry.json"
        model_registry_path = Path(tmp) / "model_registry.json"
        model_dir = Path(tmp) / "models"

        dataset_path.write_text(json.dumps({
            "registry_version": "smfp_dataset_registry_v1",
            "feature_schema_version": "smfp_features_v1",
            "labels": ["openai_like", "camera_real", "unknown"],
            "samples": samples,
        }), encoding="utf-8")
        model_registry_path.write_text(json.dumps({
            "registry_version": "smfp_model_registry_v1",
            "active_model": None,
            "ml_classifier_status": "disabled",
            "models": [],
        }), encoding="utf-8")

        training_svc = SmfpTrainingService(
            dataset_registry_path=dataset_path,
            model_registry_path=model_registry_path,
            model_dir=model_dir,
        )
        result = training_svc.train_baseline(SmfpBaselineTrainRequest())

        review_svc = SmfpReviewService(
            model_registry_path=model_registry_path,
            model_dir=model_dir,
            training_service=training_svc,
            required_approvals=1,
            governance_profile="lab",
        )
        return review_svc, result.model_id

    def _load_registry(self, tmp: str) -> dict:
        return json.loads((Path(tmp) / "model_registry.json").read_text(encoding="utf-8"))

    def _sample(self, prefix: str, label: str, split: str) -> dict:
        return {
            "sample_id": f"smfp_sample_{prefix}",
            "file_hash": prefix * 16,
            "filename": f"{prefix}.png",
            "mime_type": "image/png",
            "label": label,
            "split": split,
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
