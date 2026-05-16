import json
import tempfile
import unittest
from pathlib import Path

from app.schemas.smfp_training import SmfpBaselineTrainRequest, SmfpPromoteRequest
from app.services.smfp_training_service import SmfpTrainingService


class SmfpTrainingServiceTest(unittest.TestCase):
    """Tests for SMFP v1.8 Baseline Trainer.

    Design invariants verified:
    - Baseline model is registered but NEVER promoted.
    - active_model remains null after training.
    - ml_classifier_status remains disabled.
    - No Localization/Rubric/SxS modules are touched.
    """

    # ------------------------------------------------------------------
    # Failure cases
    # ------------------------------------------------------------------

    def test_train_fails_with_empty_dataset(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = self._service(tmp, samples=[])

            with self.assertRaises(ValueError) as ctx:
                service.train_baseline(SmfpBaselineTrainRequest())

            self.assertIn("no eligible samples", str(ctx.exception))

    def test_train_fails_with_all_unassigned_split(self) -> None:
        """Samples with split=unassigned are excluded; if all are unassigned → failure."""
        with tempfile.TemporaryDirectory() as tmp:
            samples = [
                self._sample("a", "openai_like", "unassigned"),
                self._sample("b", "camera_real", "unassigned"),
                self._sample("c", "openai_like", "unassigned"),
                self._sample("d", "camera_real", "unassigned"),
            ]
            service = self._service(tmp, samples=samples)

            with self.assertRaises(ValueError) as ctx:
                service.train_baseline(SmfpBaselineTrainRequest())

            self.assertIn("no eligible samples", str(ctx.exception))

    def test_train_fails_with_single_label(self) -> None:
        """Must have at least 2 distinct labels to train a classifier."""
        with tempfile.TemporaryDirectory() as tmp:
            samples = [
                self._sample("a", "openai_like", "train"),
                self._sample("b", "openai_like", "train"),
                self._sample("c", "openai_like", "val"),
            ]
            service = self._service(tmp, samples=samples)

            with self.assertRaises(ValueError) as ctx:
                service.train_baseline(SmfpBaselineTrainRequest())

            self.assertIn("at least 2 distinct labels", str(ctx.exception))

    def test_train_fails_with_insufficient_samples_per_label(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            samples = [
                self._sample("a", "openai_like", "train"),
                self._sample("b", "openai_like", "train"),
                self._sample("c", "openai_like", "val"),
                self._sample("d", "camera_real", "train"),  # only 1 camera_real
            ]
            service = self._service(tmp, samples=samples)

            with self.assertRaises(ValueError) as ctx:
                service.train_baseline(SmfpBaselineTrainRequest(min_samples_per_label=3))

            self.assertIn("insufficient samples per label", str(ctx.exception))
            self.assertIn("camera_real", str(ctx.exception))

    # ------------------------------------------------------------------
    # Success cases
    # ------------------------------------------------------------------

    def test_train_baseline_with_valid_dataset(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            samples = self._minimal_valid_dataset()
            service = self._service(tmp, samples=samples)

            result = service.train_baseline(SmfpBaselineTrainRequest())

            self.assertEqual(result.status, "baseline")
            self.assertEqual(result.algorithm, "random_forest")
            self.assertGreaterEqual(result.accuracy, 0.0)
            self.assertLessEqual(result.accuracy, 1.0)
            self.assertGreaterEqual(result.macro_f1, 0.0)
            self.assertEqual(result.feature_schema_version, "smfp_features_v1")
            self.assertGreater(len(result.feature_columns), 0)
            self.assertGreater(len(result.confusion_matrix), 0)
            self.assertEqual(len(result.confusion_matrix_labels), 2)
            self.assertEqual(result.training_samples_used, 6)
            self.assertEqual(result.labels_used, 2)
            self.assertIn("openai_like", result.per_label_counts)
            self.assertIn("camera_real", result.per_label_counts)

            # Model artifact exists
            self.assertTrue(Path(result.model_path).exists())
            self.assertTrue(Path(result.metadata_path).exists())

    def test_logistic_regression_algorithm(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = self._service(tmp, samples=self._minimal_valid_dataset())

            result = service.train_baseline(
                SmfpBaselineTrainRequest(algorithm="logistic_regression")
            )

            self.assertEqual(result.algorithm, "logistic_regression")
            self.assertEqual(result.status, "baseline")
            self.assertTrue(Path(result.model_path).exists())

    def test_unassigned_split_excluded(self) -> None:
        """Unassigned samples are ignored; only train/val/test count."""
        with tempfile.TemporaryDirectory() as tmp:
            samples = self._minimal_valid_dataset() + [
                self._sample("extra1", "openai_like", "unassigned"),
                self._sample("extra2", "camera_real", "unassigned"),
            ]
            service = self._service(tmp, samples=samples)

            result = service.train_baseline(SmfpBaselineTrainRequest())

            # The 2 unassigned samples should NOT appear
            self.assertEqual(result.training_samples_used, 6)
            self.assertNotIn("unassigned", result.split_distribution)

    # ------------------------------------------------------------------
    # Registry integrity
    # ------------------------------------------------------------------

    def test_model_registered_in_registry(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = self._service(tmp, samples=self._minimal_valid_dataset())

            result = service.train_baseline(SmfpBaselineTrainRequest())

            registry = json.loads(
                (Path(tmp) / "model_registry.json").read_text(encoding="utf-8")
            )
            self.assertIsNone(registry["active_model"])
            self.assertEqual(registry["ml_classifier_status"], "disabled")
            self.assertEqual(len(registry["models"]), 1)
            self.assertEqual(registry["models"][0]["model_id"], result.model_id)
            self.assertEqual(registry["models"][0]["status"], "baseline")

    def test_metadata_sidecar_contains_required_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = self._service(tmp, samples=self._minimal_valid_dataset())

            result = service.train_baseline(SmfpBaselineTrainRequest())

            metadata = json.loads(Path(result.metadata_path).read_text(encoding="utf-8"))
            self.assertIn("feature_columns", metadata)
            self.assertIn("label_encoder_mapping", metadata)
            self.assertIn("dataset_hash", metadata)
            self.assertIn("training_sample_ids", metadata)
            self.assertIn("split_distribution", metadata)
            self.assertIn("feature_schema_version", metadata)
            self.assertEqual(metadata["status"], "baseline")
            self.assertIsInstance(metadata["feature_columns"], list)
            self.assertIsInstance(metadata["label_encoder_mapping"], dict)
            self.assertEqual(len(metadata["training_sample_ids"]), 6)

    # ------------------------------------------------------------------
    # Isolation guarantees
    # ------------------------------------------------------------------

    def test_does_not_alter_rubric_lab_sxs(self) -> None:
        """Verify the training service has NO imports from Localization, Rubric, or SxS."""
        import inspect
        source = inspect.getsource(SmfpTrainingService)

        for forbidden in [
            "localization",
            "rubric",
            "sxs",
            "AnnotationSxS",
            "RubricGeneration",
            "LocalizationService",
        ]:
            self.assertNotIn(
                forbidden.lower(),
                source.lower(),
                f"SmfpTrainingService must not reference '{forbidden}'",
            )

    def test_does_not_set_active_model(self) -> None:
        """Even after training, active_model must stay null."""
        with tempfile.TemporaryDirectory() as tmp:
            service = self._service(tmp, samples=self._minimal_valid_dataset())
            service.train_baseline(SmfpBaselineTrainRequest())

            registry = json.loads(
                (Path(tmp) / "model_registry.json").read_text(encoding="utf-8")
            )
            self.assertIsNone(registry["active_model"])
            self.assertEqual(registry["ml_classifier_status"], "disabled")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _minimal_valid_dataset(self) -> list[dict]:
        """3 openai_like + 3 camera_real → meets min_samples_per_label=3."""
        return [
            self._sample("a1", "openai_like", "train"),
            self._sample("a2", "openai_like", "train"),
            self._sample("a3", "openai_like", "val"),
            self._sample("b1", "camera_real", "train"),
            self._sample("b2", "camera_real", "train"),
            self._sample("b3", "camera_real", "test"),
        ]

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
                "identity": {
                    "filename": f"{prefix}.png",
                    "mime_type": "image/png",
                    "content_hash_present": True,
                    "content_hash_prefix": "abc123",
                },
                "metadata_features": {
                    "metadata_signal_count": 2,
                    "metadata_matched_count": 1,
                    "software_tag_count": 1,
                    "creation_tool_hint": "openai_like" if "a" in prefix else "camera",
                    "has_exif": "a" not in prefix,
                    "has_xmp": False,
                    "has_pdf_metadata": False,
                    "png_text_chunk_count": 1 if "a" in prefix else 0,
                },
                "origin_heuristic_features": {
                    "likely_producer": label,
                    "origin_confidence_retained_for_audit_only": 0.4,
                    "origin_signal_count": 2,
                    "origin_matched_count": 1,
                    "attribution_level": "heuristic",
                },
                "frequency_features": {
                    "frequency_signal_count": 1,
                    "frequency_matched_count": 1,
                    "synthetic_likelihood_retained_for_audit_only": 0.6 if "a" in prefix else 0.1,
                    "camera_likelihood_retained_for_audit_only": 0.2 if "a" in prefix else 0.8,
                    "analysis_level": "frequency_heuristic",
                },
                "dimensions": {
                    "width": 1024,
                    "height": 1024,
                    "aspect_ratio": 1.0,
                },
                "mime_type_features": {
                    "is_image": True,
                    "is_png": True,
                    "is_jpeg": False,
                    "is_pdf": False,
                },
                "compression_hints": {
                    "png_chunk_count": 5,
                    "has_png_text_chunks": "a" in prefix,
                    "jpeg_exif_present": False,
                },
                "provenance_flags": {
                    "has_manifest": True,
                    "content_hash_valid": True,
                    "signature_valid": True,
                    "chain_valid": True,
                    "key_status": "active",
                    "tampering": "none",
                    "signature_algorithm": "Ed25519",
                },
            },
        }

    def _service(self, tmp: str, samples: list[dict]) -> SmfpTrainingService:
        dataset_path = Path(tmp) / "dataset_registry.json"
        model_registry_path = Path(tmp) / "model_registry.json"
        model_dir = Path(tmp) / "models"

        dataset_path.write_text(
            json.dumps(
                {
                    "registry_version": "smfp_dataset_registry_v1",
                    "feature_schema_version": "smfp_features_v1",
                    "labels": [
                        "openai_like",
                        "midjourney_like",
                        "flux_like",
                        "stable_diffusion_like",
                        "gemini_like",
                        "camera_real",
                        "unknown",
                    ],
                    "samples": samples,
                }
            ),
            encoding="utf-8",
        )
        model_registry_path.write_text(
            json.dumps(
                {
                    "registry_version": "smfp_model_registry_v1",
                    "active_model": None,
                    "ml_classifier_status": "disabled",
                    "models": [],
                }
            ),
            encoding="utf-8",
        )
        return SmfpTrainingService(
            dataset_registry_path=dataset_path,
            model_registry_path=model_registry_path,
            model_dir=model_dir,
        )


class SmfpPromotionGateTest(unittest.TestCase):
    """Tests for SMFP v1.9.1 Model Promotion Gate."""

    def test_promote_valid_baseline_model(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service, model_id = self._train_baseline(tmp)
            result = service.promote_model(model_id, SmfpPromoteRequest())

            self.assertEqual(result.model_id, model_id)
            self.assertEqual(result.status, "active")
            self.assertEqual(result.promoted_by["actor_type"], "human")
            self.assertEqual(result.promoted_by["actor_source"], "local_lab")
            self.assertEqual(result.ml_classifier_status, "active")
            self.assertIsNotNone(result.promoted_at)
            self.assertGreater(len(result.feature_columns), 0)

            registry = self._load_registry(tmp)
            self.assertEqual(registry["active_model"], model_id)
            self.assertEqual(registry["ml_classifier_status"], "active")

    def test_promote_blocks_model_not_found(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service, _ = self._train_baseline(tmp)
            with self.assertRaises(KeyError) as ctx:
                service.promote_model("nonexistent_model", SmfpPromoteRequest())
            self.assertIn("not found", str(ctx.exception))

    def test_promote_blocks_bad_metrics(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service, model_id = self._train_baseline(tmp)
            # Tamper with registry to simulate weak model metrics
            reg_path = Path(tmp) / "model_registry.json"
            reg = json.loads(reg_path.read_text(encoding="utf-8"))
            for m in reg["models"]:
                if m["model_id"] == model_id:
                    m["accuracy"] = 0.3
                    m["macro_f1"] = 0.2
            reg_path.write_text(json.dumps(reg), encoding="utf-8")

            with self.assertRaises(ValueError) as ctx:
                service.promote_model(model_id, SmfpPromoteRequest())
            self.assertIn("does not meet quality gates", str(ctx.exception))

    def test_promote_blocks_missing_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service, model_id = self._train_baseline(tmp)
            # Delete the .joblib artifact
            model_dir = Path(tmp) / "models"
            for f in model_dir.glob("*.joblib"):
                f.unlink()

            with self.assertRaises(FileNotFoundError) as ctx:
                service.promote_model(model_id, SmfpPromoteRequest())
            self.assertIn("not found", str(ctx.exception))

    def test_promote_blocks_already_active(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service, model_id = self._train_baseline(tmp)
            service.promote_model(model_id, SmfpPromoteRequest())
            # Try to promote the same model again — now status is "active"
            with self.assertRaises(ValueError) as ctx:
                service.promote_model(model_id, SmfpPromoteRequest())
            self.assertIn("Only models with status", str(ctx.exception))

    def test_previous_active_model_becomes_retired(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service, model_id_1 = self._train_baseline(tmp)
            service.promote_model(model_id_1, SmfpPromoteRequest())

            # Train and promote a second model
            result_2 = service.train_baseline(SmfpBaselineTrainRequest())
            model_id_2 = result_2.model_id
            promo = service.promote_model(model_id_2, SmfpPromoteRequest())

            self.assertEqual(promo.previous_active_model, model_id_1)
            self.assertTrue(promo.previous_active_retired)

            registry = self._load_registry(tmp)
            self.assertEqual(registry["active_model"], model_id_2)
            statuses = {m["model_id"]: m["status"] for m in registry["models"]}
            self.assertEqual(statuses[model_id_1], "retired")
            self.assertEqual(statuses[model_id_2], "active")

    def test_promote_blocks_insufficient_labels(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service, model_id = self._train_baseline(tmp)
            with self.assertRaises(ValueError) as ctx:
                service.promote_model(
                    model_id, SmfpPromoteRequest(min_labels=99)
                )
            self.assertIn("labels_used", str(ctx.exception))

    def test_auto_snapshot_failure_does_not_block_successful_promotion(self) -> None:
        class FailingSnapshotService:
            def create_snapshot_best_effort(self, payload):
                raise RuntimeError("snapshot storage unavailable")

        with tempfile.TemporaryDirectory() as tmp:
            service, model_id = self._train_baseline(tmp)
            service.snapshot_service = FailingSnapshotService()

            with self.assertLogs("app.services.smfp_training_service", level="WARNING") as logs:
                result = service.promote_model(model_id, SmfpPromoteRequest())

            self.assertEqual(result.model_id, model_id)
            self.assertEqual(result.status, "active")
            self.assertTrue(any("Best-effort governance snapshot failed" in line for line in logs.output))

            registry = self._load_registry(tmp)
            self.assertEqual(registry["active_model"], model_id)
            self.assertEqual(registry["ml_classifier_status"], "active")

    # -- helpers --

    def _train_baseline(self, tmp: str) -> tuple[SmfpTrainingService, str]:
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
        if not model_registry_path.exists():
            model_registry_path.write_text(json.dumps({
                "registry_version": "smfp_model_registry_v1",
                "active_model": None,
                "ml_classifier_status": "disabled",
                "models": [],
            }), encoding="utf-8")
        service = SmfpTrainingService(
            dataset_registry_path=dataset_path,
            model_registry_path=model_registry_path,
            model_dir=model_dir,
        )
        result = service.train_baseline(SmfpBaselineTrainRequest())
        return service, result.model_id

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
