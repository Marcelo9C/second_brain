import json
import tempfile
import unittest
from pathlib import Path

from pydantic import ValidationError

from app.schemas.smfp_ml import SmfpDatasetSampleCreate, SmfpDatasetSampleUpdate, SmfpMlFeatureExportRequest
from app.services.smfp_ml_service import SmfpMlService


class SmfpMlServiceTest(unittest.TestCase):
    def test_feature_export_is_features_only_no_model(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dataset_registry = Path(tmp) / "dataset_registry.json"
            model_registry = Path(tmp) / "model_registry.json"
            dataset_registry.write_text(
                json.dumps({"registry_version": "test_dataset", "labels": ["openai_like"]}),
                encoding="utf-8",
            )
            model_registry.write_text(
                json.dumps({"registry_version": "test_model", "active_model": None}),
                encoding="utf-8",
            )
            service = SmfpMlService(
                dataset_registry_path=dataset_registry,
                model_registry_path=model_registry,
            )

            result = service.export_features(
                SmfpMlFeatureExportRequest(
                    filename="ChatGPT Image.png",
                    mime_type="image/png",
                    content_hash="a" * 64,
                    metadata_extraction={
                        "extracted": {
                            "software": ["openai"],
                            "creation_tool": "openai_like",
                            "dimensions": {"width": 1024, "height": 1024},
                            "png_chunks": [{"type": "tEXt"}],
                        },
                        "signals": [{"type": "software_tag", "matched": True}],
                    },
                    origin_analysis={
                        "likely_producer": "openai_like",
                        "confidence": 0.41,
                        "evidence": [{"type": "filename_signal", "matched": True}],
                    },
                    frequency_analysis={
                        "synthetic_likelihood": 0.52,
                        "camera_likelihood": 0.31,
                        "signals": [{"type": "spectral_anomaly", "value": 0.8, "matched": True}],
                    },
                    provenance_verification={
                        "content_hash_valid": True,
                        "signature_valid": True,
                        "chain_valid": True,
                        "key_status": "active",
                    },
                    label=None,
                )
            )

            self.assertEqual(result["feature_schema_version"], "smfp_features_v1")
            self.assertEqual(result["label"], None)
            self.assertEqual(result["ml_status"], "features_only_no_model")
            self.assertEqual(result["ml_classifier"], "disabled")
            self.assertNotIn("ml_probability", result)
            self.assertEqual(result["features"]["dimensions"]["aspect_ratio"], 1)
            self.assertTrue(result["features"]["provenance_flags"]["signature_valid"])
            self.assertEqual(result["dataset_registry"]["registry_version"], "test_dataset")
            self.assertEqual(result["model_registry"]["registry_version"], "test_model")
            self.assertIn("No ML probability is exposed", result["limitations"])

    def test_dataset_sample_crud_and_duplicate_guard(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = self._service(tmp)

            unlabeled = service.create_sample(
                SmfpDatasetSampleCreate(
                    file_hash="a" * 64,
                    filename="unlabeled.png",
                    mime_type="image/png",
                    features={"x": 1},
                )
            )
            labeled = service.create_sample(
                SmfpDatasetSampleCreate(
                    file_hash="b" * 64,
                    filename="openai.png",
                    mime_type="image/png",
                    label="openai_like",
                    split="train",
                    source="lab",
                    license="internal-review",
                    features={"x": 2},
                )
            )

            self.assertIsNone(unlabeled["label"])
            self.assertEqual(labeled["label"], "openai_like")
            self.assertEqual(len(service.list_samples()["samples"]), 2)

            with self.assertRaises(ValueError):
                service.create_sample(
                    SmfpDatasetSampleCreate(
                        file_hash="b" * 64,
                        label="openai_like",
                    )
                )

            updated = service.update_sample(
                unlabeled["sample_id"],
                SmfpDatasetSampleUpdate(label="camera_real", split="val"),
            )
            self.assertEqual(updated["label"], "camera_real")
            self.assertEqual(updated["split"], "val")

    def test_invalid_label_is_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            SmfpDatasetSampleCreate(file_hash="c" * 64, label="not_a_label")

    def test_dataset_summary_empty_dataset(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            summary = self._service(tmp).dataset_summary()

            self.assertEqual(summary["total_samples"], 0)
            self.assertEqual(summary["unlabeled_count"], 0)
            self.assertEqual(summary["samples_by_split"]["train"], 0)
            self.assertIn("No labeled samples yet.", summary["label_balance_warnings"])
            self.assertIn("No assigned train/val/test samples yet.", summary["split_balance_warnings"])
            self.assertEqual(summary["ml_status"], "dataset_quality_only_no_model")

    def test_dataset_summary_balanced_labels(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = self._service(tmp)
            service.create_sample(self._sample("a", "openai_like", "train"))
            service.create_sample(self._sample("b", "camera_real", "val"))
            service.create_sample(self._sample("c", "unknown", "test"))

            summary = service.dataset_summary()

            self.assertEqual(summary["total_samples"], 3)
            self.assertEqual(summary["samples_by_label"]["openai_like"], 1)
            self.assertEqual(summary["samples_by_label"]["camera_real"], 1)
            self.assertEqual(summary["samples_by_label"]["unknown"], 1)
            self.assertEqual(summary["samples_by_split"]["train"], 1)
            self.assertNotIn("Dominant label", " ".join(summary["label_balance_warnings"]))
            self.assertEqual(summary["split_balance_warnings"], [])

    def test_dataset_summary_warns_for_dominant_label(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = self._service(tmp)
            service.create_sample(self._sample("a", "openai_like", "train"))
            service.create_sample(self._sample("b", "openai_like", "val"))
            service.create_sample(self._sample("c", "openai_like", "test"))
            service.create_sample(self._sample("d", "camera_real", "train"))

            summary = service.dataset_summary()

            self.assertTrue(
                any("Dominant label: openai_like" in warning for warning in summary["label_balance_warnings"])
            )

    def test_dataset_summary_warns_for_missing_split(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = self._service(tmp)
            service.create_sample(self._sample("a", "openai_like", "train"))

            summary = service.dataset_summary()

            self.assertIn("Missing split: val.", summary["split_balance_warnings"])
            self.assertIn("Missing split: test.", summary["split_balance_warnings"])

    def test_dataset_summary_counts_missing_features(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = self._service(tmp)
            service.create_sample(
                SmfpDatasetSampleCreate(
                    file_hash="f" * 64,
                    label="unknown",
                    split="train",
                    features={"identity": {"filename": "missing.png"}},
                )
            )

            summary = service.dataset_summary()

            self.assertEqual(summary["missing_feature_counts"]["frequency_features"], 1)
            self.assertEqual(summary["missing_feature_counts"]["metadata_features"], 1)
            self.assertNotIn("identity", summary["missing_feature_counts"])

    def _sample(self, prefix: str, label: str, split: str) -> SmfpDatasetSampleCreate:
        return SmfpDatasetSampleCreate(
            file_hash=prefix * 64,
            label=label,
            split=split,
            features={
                "identity": {"filename": f"{prefix}.png"},
                "metadata_features": {"metadata_signal_count": 1},
                "origin_heuristic_features": {"likely_producer": label},
                "frequency_features": {"frequency_signal_count": 1},
                "dimensions": {"width": 1024, "height": 1024},
                "mime_type_features": {"is_image": True},
                "compression_hints": {"png_chunk_count": 1},
                "provenance_flags": {"has_manifest": True},
            },
        )

    def _service(self, tmp: str) -> SmfpMlService:
        dataset_registry = Path(tmp) / "dataset_registry.json"
        model_registry = Path(tmp) / "model_registry.json"
        dataset_registry.write_text(
            json.dumps(
                {
                    "registry_version": "test_dataset",
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
                    "samples": [],
                }
            ),
            encoding="utf-8",
        )
        model_registry.write_text(
            json.dumps({"registry_version": "test_model", "active_model": None}),
            encoding="utf-8",
        )
        return SmfpMlService(
            dataset_registry_path=dataset_registry,
            model_registry_path=model_registry,
        )
