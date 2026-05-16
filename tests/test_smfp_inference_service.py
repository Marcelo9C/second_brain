import json
import tempfile
import unittest
from pathlib import Path

import joblib
from sklearn.ensemble import RandomForestClassifier

from app.schemas.smfp_inference import SmfpMlInferenceRequest
from app.services.smfp_inference_service import SmfpInferenceService
from app.services.smfp_ml_service import SmfpMlService


class SmfpInferenceServiceTest(unittest.TestCase):
    def test_without_active_model_returns_disabled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = self._service(tmp)

            result = service.infer(self._payload()).model_dump()

            self.assertEqual(result["ml_status"], "disabled")
            self.assertEqual(result["predictions"], [])
            self.assertIn("no active_model", " ".join(result["limitations"]))

    def test_active_model_with_missing_artifact_returns_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self._write_registry(tmp, active_model="smfp_model_missing", model_file="missing.joblib")
            service = self._service(tmp)

            result = service.infer(self._payload()).model_dump()

            self.assertEqual(result["ml_status"], "error")
            self.assertIn("artifact not found", " ".join(result["limitations"]))

    def test_schema_mismatch_returns_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = self._service(tmp)
            self._promote_valid_model(tmp, service, feature_schema_version="smfp_features_v0")

            result = service.infer(self._payload()).model_dump()

            self.assertEqual(result["ml_status"], "error")
            self.assertIn("Feature schema mismatch", " ".join(result["limitations"]))

    def test_feature_column_mismatch_returns_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = self._service(tmp)
            self._promote_valid_model(tmp, service, feature_columns=["dimensions.width"])

            result = service.infer(self._payload()).model_dump()

            self.assertEqual(result["ml_status"], "error")
            self.assertIn("Feature columns mismatch", " ".join(result["limitations"]))

    def test_valid_active_model_returns_top_k_predictions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = self._service(tmp)
            self._promote_valid_model(tmp, service)

            result = service.infer(self._payload(top_k=2)).model_dump()

            self.assertEqual(result["ml_status"], "active")
            self.assertEqual(result["model_id"], "smfp_model_active")
            self.assertEqual(len(result["predictions"]), 2)
            self.assertIn(result["predictions"][0]["label"], {"openai_like", "camera_real"})
            self.assertIn("ML probability is separate from Origin Confidence", result["limitations"])

    def test_trust_and_origin_heuristic_are_not_altered(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = self._service(tmp)
            self._promote_valid_model(tmp, service)

            result = service.infer(self._payload()).model_dump()

            self.assertEqual(result["details"]["origin_confidence_preserved"], 0.41)
            self.assertEqual(result["details"]["trust_score_preserved"], 88)
            self.assertNotIn("origin_confidence", result)
            self.assertNotIn("trust_score", result)

    def _service(self, tmp: str) -> SmfpInferenceService:
        root = Path(tmp)
        dataset_registry_path = root / "dataset_registry.json"
        model_registry_path = root / "model_registry.json"
        dataset_registry_path.write_text(
            json.dumps({"registry_version": "test_dataset", "samples": []}),
            encoding="utf-8",
        )
        if not model_registry_path.exists():
            self._write_registry(tmp, active_model=None)
        ml_service = SmfpMlService(
            dataset_registry_path=dataset_registry_path,
            model_registry_path=model_registry_path,
        )
        return SmfpInferenceService(
            ml_service=ml_service,
            model_registry_path=model_registry_path,
            model_dir=root,
        )

    def _write_registry(self, tmp: str, *, active_model: str | None, model_file: str | None = None) -> None:
        models = []
        if active_model:
            models.append(
                {
                    "model_id": active_model,
                    "model_file": model_file or f"{active_model}.joblib",
                    "model_version": "v-test",
                    "status": "promoted",
                }
            )
        (Path(tmp) / "model_registry.json").write_text(
            json.dumps(
                {
                    "registry_version": "test_model",
                    "feature_schema_version": "smfp_features_v1",
                    "active_model": active_model,
                    "ml_classifier_status": "active" if active_model else "disabled",
                    "models": models,
                }
            ),
            encoding="utf-8",
        )

    def _promote_valid_model(
        self,
        tmp: str,
        service: SmfpInferenceService,
        *,
        feature_schema_version: str = "smfp_features_v1",
        feature_columns: list[str] | None = None,
    ) -> None:
        payload = self._payload()
        features = service.ml_service.export_features(payload)["features"]
        columns = feature_columns or service._discover_feature_columns(features)
        row = [service._feature_value(features, column) for column in columns]
        alternate = [0.0 for _ in columns]
        model = RandomForestClassifier(n_estimators=5, random_state=42)
        model.fit([row, alternate], [0, 1])

        model_id = "smfp_model_active"
        joblib.dump(model, Path(tmp) / f"{model_id}.joblib")
        (Path(tmp) / f"{model_id}_metadata.json").write_text(
            json.dumps(
                {
                    "model_id": model_id,
                    "model_version": "v-test",
                    "feature_schema_version": feature_schema_version,
                    "feature_columns": columns,
                    "label_encoder_mapping": {"openai_like": 0, "camera_real": 1},
                    "trained_at": "2026-05-15T00:00:00+00:00",
                }
            ),
            encoding="utf-8",
        )
        self._write_registry(tmp, active_model=model_id)

    def _payload(self, *, top_k: int = 3) -> SmfpMlInferenceRequest:
        return SmfpMlInferenceRequest(
            filename="ChatGPT Image 15 de mai.png",
            mime_type="image/png",
            content_hash="a" * 64,
            metadata_extraction={
                "extracted": {
                    "software": ["ChatGPT"],
                    "creation_tool": "openai_like",
                    "dimensions": {"width": 1024, "height": 1024},
                    "png_chunks": [{"type": "tEXt"}],
                },
                "signals": [{"type": "png_text_chunk", "matched": True}],
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
                "tampering": "none",
                "signature_algorithm": "Ed25519",
                "trust_score": 88,
            },
            manifest={"asset_id": "asset-test"},
            top_k=top_k,
        )
