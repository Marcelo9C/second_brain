from __future__ import annotations

import hashlib
import json
import logging
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import joblib
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score
from sklearn.preprocessing import LabelEncoder

from app.schemas.smfp_actor import SmfpActor, local_human_actor
from app.schemas.smfp_training import (
    SmfpBaselineTrainRequest,
    SmfpBaselineTrainResult,
    SmfpPromoteRequest,
    SmfpPromoteResult,
)


class SmfpTrainingService:
    """Trains baseline SMFP attribution classifiers from the dataset registry.

    Design rules:
    - Baseline models are NEVER auto-promoted to production.
    - active_model in model_registry stays null after training.
    - ml_classifier_status stays disabled.
    - Inference remains disabled until explicit promotion (out of scope).
    - ML probability MUST NOT be mixed with heuristic confidence.
    """

    FEATURE_SCHEMA_VERSION = "smfp_features_v1"

    # Text / non-numeric feature keys to exclude from the flat vector.
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
        dataset_registry_path: Path,
        model_registry_path: Path,
        model_dir: Path,
        snapshot_service: Any | None = None,  # SmfpSnapshotService (optional, for auto-trigger)
    ) -> None:
        self.dataset_registry_path = dataset_registry_path
        self.model_registry_path = model_registry_path
        self.model_dir = model_dir
        self.snapshot_service = snapshot_service
        self._logger = logging.getLogger(__name__)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def train_baseline(self, request: SmfpBaselineTrainRequest) -> SmfpBaselineTrainResult:
        """Train a baseline classifier and register it (status=baseline)."""

        # 1. Load & filter samples ------------------------------------------------
        registry = self._load_json(self.dataset_registry_path)
        all_samples = registry.get("samples", [])

        samples = [
            s for s in all_samples
            if s.get("label") is not None and s.get("split") != "unassigned"
        ]

        if not samples:
            raise ValueError(
                "SMFP training failed: no eligible samples found. "
                "Samples must have a valid label and an assigned split (train/val/test)."
            )

        # 2. Count labels ---------------------------------------------------------
        label_counts: Counter[str] = Counter(s["label"] for s in samples)

        # Guard: need at least 2 distinct valid labels
        if len(label_counts) < 2:
            raise ValueError(
                f"SMFP training failed: need at least 2 distinct labels, "
                f"found {len(label_counts)} ({list(label_counts.keys())}). "
                f"Cannot train a classifier with a single class."
            )

        # Guard: minimum samples per label
        insufficient = {
            label: count
            for label, count in label_counts.items()
            if count < request.min_samples_per_label
        }
        if insufficient:
            raise ValueError(
                f"SMFP training failed: insufficient samples per label "
                f"(min_samples_per_label={request.min_samples_per_label}). "
                f"Insufficient labels: {insufficient}."
            )

        # 3. Flatten features to numeric matrix -----------------------------------
        feature_columns = self._discover_feature_columns(samples)
        X = [self._flatten_sample(s, feature_columns) for s in samples]
        labels_raw = [s["label"] for s in samples]

        label_encoder = LabelEncoder()
        y = label_encoder.fit_transform(labels_raw).tolist()

        # 4. Train model ----------------------------------------------------------
        clf = self._create_classifier(request.algorithm)
        clf.fit(X, y)

        # 5. Compute metrics (on training set — baseline diagnostic only) ---------
        y_pred = clf.predict(X)
        accuracy = float(accuracy_score(y, y_pred))
        macro_f1 = float(f1_score(y, y_pred, average="macro"))
        cm = confusion_matrix(y, y_pred).tolist()
        cm_labels = label_encoder.classes_.tolist()

        # 6. Build IDs and paths --------------------------------------------------
        now = datetime.now(timezone.utc).isoformat()
        dataset_hash = self._dataset_hash(samples)
        model_id = self._model_id(now, dataset_hash)

        self.model_dir.mkdir(parents=True, exist_ok=True)
        model_filename = f"{model_id}.joblib"
        metadata_filename = f"{model_id}_metadata.json"
        model_path = self.model_dir / model_filename
        metadata_path = self.model_dir / metadata_filename

        # 7. Save model artifact --------------------------------------------------
        joblib.dump(clf, model_path)

        # 8. Save metadata sidecar ------------------------------------------------
        split_distribution = dict(Counter(s.get("split", "unassigned") for s in samples))
        training_sample_ids = [s.get("sample_id", "unknown") for s in samples]
        label_mapping = {
            label: int(idx) for label, idx in zip(
                label_encoder.classes_.tolist(),
                label_encoder.transform(label_encoder.classes_).tolist(),
            )
        }

        metadata = {
            "model_id": model_id,
            "algorithm": request.algorithm,
            "status": "baseline",
            "trained_at": now,
            "feature_schema_version": self.FEATURE_SCHEMA_VERSION,
            "feature_columns": feature_columns,
            "label_encoder_mapping": label_mapping,
            "dataset_hash": dataset_hash,
            "training_sample_ids": training_sample_ids,
            "split_distribution": split_distribution,
            "per_label_counts": dict(label_counts),
            "accuracy": accuracy,
            "macro_f1": macro_f1,
            "confusion_matrix": cm,
            "confusion_matrix_labels": cm_labels,
            "model_file": model_filename,
            "min_samples_per_label": request.min_samples_per_label,
            "training_samples_used": len(samples),
            "labels_used": len(label_counts),
        }

        metadata_path.write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )

        # 9. Register in model_registry.json (DO NOT promote) ---------------------
        self._register_model(metadata)

        # 10. Return result -------------------------------------------------------
        return SmfpBaselineTrainResult(
            model_id=model_id,
            algorithm=request.algorithm,
            accuracy=accuracy,
            macro_f1=macro_f1,
            per_label_counts=dict(label_counts),
            confusion_matrix=cm,
            confusion_matrix_labels=cm_labels,
            feature_schema_version=self.FEATURE_SCHEMA_VERSION,
            feature_columns=feature_columns,
            trained_at=now,
            model_path=str(model_path),
            metadata_path=str(metadata_path),
            training_samples_used=len(samples),
            labels_used=len(label_counts),
            split_distribution=split_distribution,
        )

    def promote_model(
        self,
        model_id: str,
        request: SmfpPromoteRequest,
        *,
        actor: SmfpActor | None = None,
    ) -> SmfpPromoteResult:
        """Promote a baseline or candidate model to active after passing quality gates.

        State machine:
            baseline / candidate  →  active
            (previous active)     →  retired
        """
        if actor is None:
            actor = local_human_actor()

        # 1. Load registry and find the model entry ----------------------------
        registry = self._load_json(self.model_registry_path)
        models = registry.get("models", [])

        target = None
        for entry in models:
            if entry.get("model_id") == model_id:
                target = entry
                break

        if target is None:
            raise KeyError(
                f"SMFP promotion failed: model '{model_id}' not found in model_registry."
            )

        # 2. Check promotable status -------------------------------------------
        current_status = target.get("status", "unknown")
        if current_status not in ("baseline", "candidate"):
            raise ValueError(
                f"SMFP promotion failed: model '{model_id}' has status '{current_status}'. "
                f"Only models with status 'baseline' or 'candidate' can be promoted."
            )

        # 3. Validate model artifact exists ------------------------------------
        model_file = target.get("model_file", "")
        model_path = self.model_dir / model_file
        if not model_file or not model_path.exists():
            raise FileNotFoundError(
                f"SMFP promotion failed: model artifact '{model_file}' not found at {model_path}."
            )

        # 4. Load metadata sidecar for full validation -------------------------
        metadata_filename = model_file.replace(".joblib", "_metadata.json")
        metadata_path = self.model_dir / metadata_filename
        if not metadata_path.exists():
            raise FileNotFoundError(
                f"SMFP promotion failed: metadata sidecar '{metadata_filename}' not found."
            )

        metadata = self._load_json(metadata_path)

        # 5. Validate feature_columns and dataset_hash -------------------------
        feature_columns = metadata.get("feature_columns", [])
        if not feature_columns:
            raise ValueError(
                f"SMFP promotion failed: model '{model_id}' has no feature_columns in metadata. "
                f"Cannot guarantee inference column order."
            )

        dataset_hash = metadata.get("dataset_hash")
        if not dataset_hash:
            raise ValueError(
                f"SMFP promotion failed: model '{model_id}' has no dataset_hash in metadata."
            )

        # 6. Check metric thresholds -------------------------------------------
        accuracy = target.get("accuracy", 0.0)
        macro_f1 = target.get("macro_f1", 0.0)
        labels_used = target.get("labels_used", 0)
        feature_schema_version = target.get("feature_schema_version", "unknown")

        gate_failures: list[str] = []
        if macro_f1 < request.min_macro_f1:
            gate_failures.append(
                f"macro_f1={macro_f1:.4f} < min_macro_f1={request.min_macro_f1}"
            )
        if accuracy < request.min_accuracy:
            gate_failures.append(
                f"accuracy={accuracy:.4f} < min_accuracy={request.min_accuracy}"
            )
        if labels_used < request.min_labels:
            gate_failures.append(
                f"labels_used={labels_used} < min_labels={request.min_labels}"
            )

        if gate_failures:
            raise ValueError(
                f"SMFP promotion failed: model '{model_id}' does not meet quality gates. "
                f"Failures: {'; '.join(gate_failures)}."
            )

        # 7. Retire the current active model (if any) --------------------------
        now = datetime.now(timezone.utc).isoformat()
        previous_active = registry.get("active_model")
        previous_retired = False

        if previous_active is not None:
            for entry in models:
                if entry.get("model_id") == previous_active and entry.get("status") == "active":
                    entry["status"] = "retired"
                    entry["retired_at"] = now
                    previous_retired = True
                    break

        # 8. Promote the target model ------------------------------------------
        actor_dict = actor.model_dump()
        target["status"] = "active"
        target["promoted_at"] = now
        target["promoted_by"] = actor_dict

        registry["active_model"] = model_id
        registry["ml_classifier_status"] = "active"

        # 9. Persist registry --------------------------------------------------
        self._write_registry(registry)

        # 10. Update metadata sidecar ------------------------------------------
        metadata["status"] = "active"
        metadata["promoted_at"] = now
        metadata["promoted_by"] = actor_dict
        metadata_path.write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )

        # 11. Auto-snapshot: best-effort (never rolls back promotion) ----------
        if previous_retired and previous_active:
            self._auto_snapshot_retirement(previous_active, actor)
        self._auto_snapshot_promotion(model_id, actor)

        return SmfpPromoteResult(
            model_id=model_id,
            promoted_at=now,
            promoted_by=actor_dict,
            previous_active_model=previous_active,
            previous_active_retired=previous_retired,
            accuracy=accuracy,
            macro_f1=macro_f1,
            labels_used=labels_used,
            feature_schema_version=feature_schema_version,
            feature_columns=feature_columns,
        )

    def _auto_snapshot_promotion(self, model_id: str, actor: SmfpActor) -> None:
        """Best-effort governance snapshot after promotion."""
        if not self.snapshot_service:
            return
        from app.schemas.smfp_snapshot import SmfpSnapshotCreate

        try:
            self.snapshot_service.create_snapshot_best_effort(
                SmfpSnapshotCreate(
                    trigger="promotion",
                    actor=actor,
                    notes=f"Auto-snapshot after promotion of model {model_id}.",
                )
            )
        except Exception:
            self._logger.warning(
                "Best-effort governance snapshot failed after promotion of model '%s'.",
                model_id,
                exc_info=True,
            )

    def _auto_snapshot_retirement(self, model_id: str, actor: SmfpActor) -> None:
        """Best-effort governance snapshot after retirement."""
        if not self.snapshot_service:
            return
        from app.schemas.smfp_snapshot import SmfpSnapshotCreate

        try:
            self.snapshot_service.create_snapshot_best_effort(
                SmfpSnapshotCreate(
                    trigger="retirement",
                    actor=actor,
                    notes=f"Auto-snapshot after retirement of model {model_id}.",
                )
            )
        except Exception:
            self._logger.warning(
                "Best-effort governance snapshot failed after retirement of model '%s'.",
                model_id,
                exc_info=True,
            )

    # ------------------------------------------------------------------
    # Feature engineering
    # ------------------------------------------------------------------

    def _discover_feature_columns(self, samples: list[dict[str, Any]]) -> list[str]:
        """Walk all samples to discover the union of numeric feature keys."""
        columns: set[str] = set()
        for sample in samples:
            features = sample.get("features") or {}
            for group_key, group_val in features.items():
                if not isinstance(group_val, dict):
                    continue
                for key, val in group_val.items():
                    flat_key = f"{group_key}.{key}"
                    if flat_key in self._EXCLUDED_KEYS:
                        continue
                    if isinstance(val, bool | int | float):
                        columns.add(flat_key)
        return sorted(columns)

    def _flatten_sample(
        self, sample: dict[str, Any], feature_columns: list[str]
    ) -> list[float]:
        """Convert a sample's nested features to a flat numeric vector."""
        features = sample.get("features") or {}
        row: list[float] = []
        for col in feature_columns:
            group_key, key = col.split(".", 1)
            group = features.get(group_key) or {}
            val = group.get(key)
            if isinstance(val, bool):
                row.append(1.0 if val else 0.0)
            elif isinstance(val, int | float):
                row.append(float(val))
            else:
                row.append(0.0)
        return row

    # ------------------------------------------------------------------
    # Classifier factory
    # ------------------------------------------------------------------

    def _create_classifier(
        self, algorithm: str
    ) -> RandomForestClassifier | LogisticRegression:
        if algorithm == "logistic_regression":
            return LogisticRegression(max_iter=1000, random_state=42)
        return RandomForestClassifier(n_estimators=100, random_state=42)

    # ------------------------------------------------------------------
    # Registry operations
    # ------------------------------------------------------------------

    def _register_model(self, metadata: dict[str, Any]) -> None:
        """Append model entry to model_registry.json. Never promote."""
        registry = self._load_json(self.model_registry_path)
        registry.setdefault("registry_version", "smfp_model_registry_v1")
        registry.setdefault("feature_schema_version", self.FEATURE_SCHEMA_VERSION)
        registry.setdefault("models", [])

        # active_model and ml_classifier_status stay unchanged
        registry.setdefault("active_model", None)
        registry.setdefault("ml_classifier_status", "disabled")

        entry = {
            "model_id": metadata["model_id"],
            "algorithm": metadata["algorithm"],
            "status": "baseline",
            "trained_at": metadata["trained_at"],
            "feature_schema_version": metadata["feature_schema_version"],
            "model_file": metadata["model_file"],
            "accuracy": metadata["accuracy"],
            "macro_f1": metadata["macro_f1"],
            "training_samples_used": metadata["training_samples_used"],
            "labels_used": metadata["labels_used"],
            "dataset_hash": metadata["dataset_hash"],
        }
        registry["models"].append(entry)

        self._write_registry(registry)

    def _write_registry(self, registry: dict[str, Any]) -> None:
        """Persist model_registry.json to disk."""
        self.model_registry_path.parent.mkdir(parents=True, exist_ok=True)
        self.model_registry_path.write_text(
            json.dumps(registry, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _load_json(self, path: Path) -> dict[str, Any]:
        if not path.exists():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))

    def _dataset_hash(self, samples: list[dict[str, Any]]) -> str:
        ids = sorted(s.get("sample_id", "") for s in samples)
        return hashlib.sha256("|".join(ids).encode("utf-8")).hexdigest()[:16]

    def _model_id(self, timestamp: str, dataset_hash: str) -> str:
        digest = hashlib.sha256(
            f"{timestamp}:{dataset_hash}".encode("utf-8")
        ).hexdigest()[:12]
        return f"smfp_baseline_{digest}"
