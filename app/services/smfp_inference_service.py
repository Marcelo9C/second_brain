from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.schemas.smfp_inference import SmfpMlInferenceRequest, SmfpMlInferenceResult
from app.services.smfp_ml_service import SmfpMlService


class SmfpInferenceService:
    _EXCLUDED_KEYS = frozenset({
        "identity.filename",
        "identity.content_hash_prefix",
        "origin_heuristic_features.likely_producer",
        "origin_heuristic_features.attribution_level",
        "frequency_features.analysis_level",
        "metadata_features.creation_tool_hint",
        "provenance_flags.key_status",
        "provenance_flags.tampering",
        "provenance_flags.signature_algorithm",
    })

    def __init__(
        self,
        *,
        ml_service: SmfpMlService,
        model_registry_path: Path,
        model_dir: Path,
    ) -> None:
        self.ml_service = ml_service
        self.model_registry_path = model_registry_path
        self.model_dir = model_dir

    def infer(self, payload: SmfpMlInferenceRequest) -> SmfpMlInferenceResult:
        registry = self._load_registry()
        active_model = registry.get("active_model")
        if not active_model:
            return SmfpMlInferenceResult(
                ml_status="disabled",
                limitations=[
                    "ML classifier disabled: no active_model is promoted in model_registry",
                    "Origin Analysis heuristic remains separate",
                    "Trust Score remains separate from ML probability",
                ],
                details={"ml_classifier_status": registry.get("ml_classifier_status", "disabled")},
            )

        entry = self._active_entry(registry, str(active_model))
        if entry is None:
            return self._error(str(active_model), "Active model is not registered in model_registry.")

        model_path = self.model_dir / str(entry.get("model_file") or "")
        metadata_path = self.model_dir / f"{active_model}_metadata.json"
        if not model_path.exists():
            return self._error(str(active_model), f"Active model artifact not found: {model_path}.")
        if not metadata_path.exists():
            return self._error(str(active_model), f"Active model sidecar metadata not found: {metadata_path}.")

        metadata = self._load_json(metadata_path)
        feature_export = self.ml_service.export_features(payload)
        feature_schema_version = feature_export.get("feature_schema_version")
        expected_schema = metadata.get("feature_schema_version")
        if feature_schema_version != expected_schema:
            return self._error(
                str(active_model),
                f"Feature schema mismatch: payload {feature_schema_version} != model {expected_schema}.",
                model_version=self._model_version(entry, metadata),
            )

        features = feature_export.get("features") or {}
        expected_columns = list(metadata.get("feature_columns") or [])
        actual_columns = self._discover_feature_columns(features)
        if actual_columns != expected_columns:
            return self._error(
                str(active_model),
                "Feature columns mismatch with active model sidecar.",
                model_version=self._model_version(entry, metadata),
                details={"expected_feature_columns": expected_columns, "actual_feature_columns": actual_columns},
            )

        try:
            import joblib

            model = joblib.load(model_path)
        except Exception as error:
            return self._error(
                str(active_model),
                f"Failed to load active model artifact: {error.__class__.__name__}.",
                model_version=self._model_version(entry, metadata),
            )

        if not hasattr(model, "predict_proba"):
            return self._error(
                str(active_model),
                "Active model does not support predict_proba.",
                model_version=self._model_version(entry, metadata),
            )

        row = [self._feature_value(features, column) for column in expected_columns]
        probabilities = model.predict_proba([row])[0]
        labels = self._labels_for_model(model, metadata)
        predictions = sorted(
            [
                {"label": label, "probability": round(float(probability), 6)}
                for label, probability in zip(labels, probabilities)
            ],
            key=lambda item: item["probability"],
            reverse=True,
        )[: payload.top_k]

        return SmfpMlInferenceResult(
            ml_status="active",
            model_id=str(active_model),
            model_version=self._model_version(entry, metadata),
            predictions=predictions,
            limitations=[
                "ML probability is separate from Origin Confidence",
                "ML inference never replaces Provenance Verification",
                "Trust Score remains separate from ML probability",
                "Offline inference uses only the explicitly promoted active_model",
            ],
            details={
                "feature_schema_version": feature_schema_version,
                "feature_columns": expected_columns,
                "origin_confidence_preserved": payload.origin_analysis.get("confidence")
                if payload.origin_analysis
                else None,
                "trust_score_preserved": (payload.provenance_verification or {}).get("trust_score"),
            },
        )

    def _load_registry(self) -> dict[str, Any]:
        if not self.model_registry_path.exists():
            return {}
        return json.loads(self.model_registry_path.read_text(encoding="utf-8"))

    def _active_entry(self, registry: dict[str, Any], active_model: str) -> dict[str, Any] | None:
        return next((item for item in registry.get("models", []) if item.get("model_id") == active_model), None)

    def _load_json(self, path: Path) -> dict[str, Any]:
        return json.loads(path.read_text(encoding="utf-8"))

    def _discover_feature_columns(self, features: dict[str, Any]) -> list[str]:
        columns: set[str] = set()
        for group_key, group_value in features.items():
            if not isinstance(group_value, dict):
                continue
            for key, value in group_value.items():
                flat_key = f"{group_key}.{key}"
                if flat_key in self._EXCLUDED_KEYS:
                    continue
                if isinstance(value, bool | int | float):
                    columns.add(flat_key)
        return sorted(columns)

    def _feature_value(self, features: dict[str, Any], column: str) -> float:
        group_key, key = column.split(".", 1)
        value = (features.get(group_key) or {}).get(key)
        if isinstance(value, bool):
            return 1.0 if value else 0.0
        if isinstance(value, int | float):
            return float(value)
        return 0.0

    def _labels_for_model(self, model: Any, metadata: dict[str, Any]) -> list[str]:
        label_mapping = metadata.get("label_encoder_mapping") or {}
        inverse = {int(index): label for label, index in label_mapping.items()}
        classes = getattr(model, "classes_", [])
        return [inverse.get(int(item), str(item)) for item in classes]

    def _model_version(self, entry: dict[str, Any], metadata: dict[str, Any]) -> str | None:
        return entry.get("model_version") or metadata.get("model_version") or entry.get("trained_at") or metadata.get("trained_at")

    def _error(
        self,
        model_id: str | None,
        message: str,
        *,
        model_version: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> SmfpMlInferenceResult:
        return SmfpMlInferenceResult(
            ml_status="error",
            model_id=model_id,
            model_version=model_version,
            predictions=[],
            limitations=[
                message,
                "ML inference did not modify Origin Analysis heuristic output",
                "ML inference did not modify Trust Score or Provenance Verification",
            ],
            details=details or {},
        )
