from __future__ import annotations

import json
import hashlib
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.schemas.smfp_ml import SmfpDatasetSampleCreate, SmfpDatasetSampleUpdate, SmfpMlFeatureExportRequest


class SmfpMlService:
    FEATURE_SCHEMA_VERSION = "smfp_features_v1"

    def __init__(self, *, dataset_registry_path: Path, model_registry_path: Path) -> None:
        self.dataset_registry_path = dataset_registry_path
        self.model_registry_path = model_registry_path

    def export_features(self, payload: SmfpMlFeatureExportRequest) -> dict[str, Any]:
        metadata = payload.metadata_extraction or {}
        origin = payload.origin_analysis or {}
        frequency = payload.frequency_analysis or {}
        provenance = payload.provenance_verification or {}
        manifest = payload.manifest or {}

        metadata_signals = metadata.get("signals") or origin.get("metadata_signals") or []
        origin_signals = origin.get("evidence") or []
        frequency_signals = frequency.get("signals") or []
        extracted = metadata.get("extracted") or {}
        dimensions = extracted.get("dimensions") or {}

        features = {
            "identity": {
                "filename": payload.filename,
                "mime_type": payload.mime_type,
                "content_hash_present": bool(payload.content_hash),
                "content_hash_prefix": (payload.content_hash or "")[:12],
            },
            "metadata_features": {
                "metadata_signal_count": len(metadata_signals),
                "metadata_matched_count": self._matched_count(metadata_signals),
                "software_tag_count": len(extracted.get("software", [])),
                "creation_tool_hint": extracted.get("creation_tool", "unknown"),
                "has_exif": bool(extracted.get("exif")),
                "has_xmp": bool(extracted.get("xmp")),
                "has_pdf_metadata": bool(extracted.get("pdf_metadata")),
                "png_text_chunk_count": sum(
                    1 for chunk in extracted.get("png_chunks", []) if chunk.get("type") in {"tEXt", "iTXt", "zTXt"}
                ),
            },
            "origin_heuristic_features": {
                "likely_producer": origin.get("likely_producer", "unknown"),
                "origin_confidence_retained_for_audit_only": origin.get("confidence", 0.0),
                "origin_signal_count": len(origin_signals),
                "origin_matched_count": self._matched_count(origin_signals),
                "attribution_level": origin.get("attribution_level", "heuristic"),
            },
            "frequency_features": {
                "frequency_signal_count": len(frequency_signals),
                "frequency_matched_count": self._matched_count(frequency_signals),
                "synthetic_likelihood_retained_for_audit_only": frequency.get("synthetic_likelihood", 0.0),
                "camera_likelihood_retained_for_audit_only": frequency.get("camera_likelihood", 0.0),
                "analysis_level": frequency.get("analysis_level", "frequency_heuristic"),
                **self._signal_values("frequency", frequency_signals),
            },
            "dimensions": {
                "width": dimensions.get("width"),
                "height": dimensions.get("height"),
                "aspect_ratio": self._aspect_ratio(dimensions.get("width"), dimensions.get("height")),
            },
            "mime_type_features": {
                "is_image": payload.mime_type.startswith("image/"),
                "is_png": payload.mime_type == "image/png",
                "is_jpeg": payload.mime_type == "image/jpeg",
                "is_pdf": payload.mime_type == "application/pdf",
            },
            "compression_hints": {
                "png_chunk_count": len(extracted.get("png_chunks", [])),
                "has_png_text_chunks": any(
                    chunk.get("type") in {"tEXt", "iTXt", "zTXt"} for chunk in extracted.get("png_chunks", [])
                ),
                "jpeg_exif_present": bool(extracted.get("exif")),
            },
            "provenance_flags": {
                "has_manifest": bool(manifest),
                "content_hash_valid": bool(provenance.get("content_hash_valid")),
                "signature_valid": bool(provenance.get("signature_valid")),
                "chain_valid": bool(provenance.get("chain_valid")),
                "key_status": provenance.get("key_status", "unknown"),
                "tampering": provenance.get("tampering", "unknown"),
                "signature_algorithm": provenance.get("signature_algorithm", "unknown"),
            },
        }

        return {
            "feature_schema_version": self.FEATURE_SCHEMA_VERSION,
            "features": features,
            "label": payload.label,
            "ml_status": "features_only_no_model",
            "ml_classifier": "disabled",
            "dataset_registry": self._load_registry(self.dataset_registry_path),
            "model_registry": self._load_registry(self.model_registry_path),
            "limitations": [
                "No ML model is trained or enabled",
                "No ML probability is exposed",
                "Heuristic confidence values are retained as audit features only and are not ML probabilities",
                "Feature export does not modify provenance trust_score",
            ],
        }

    def _matched_count(self, signals: list[dict[str, Any]]) -> int:
        return sum(1 for signal in signals if signal.get("matched"))

    def _signal_values(self, prefix: str, signals: list[dict[str, Any]]) -> dict[str, float]:
        values: dict[str, float] = {}
        for signal in signals:
            signal_type = str(signal.get("type", "unknown")).replace("-", "_")
            value = signal.get("value")
            if isinstance(value, int | float):
                values[f"{prefix}_{signal_type}_value"] = float(value)
        return values

    def _aspect_ratio(self, width: Any, height: Any) -> float | None:
        try:
            width_value = float(width)
            height_value = float(height)
        except (TypeError, ValueError):
            return None
        if height_value == 0:
            return None
        return round(width_value / height_value, 4)

    def _load_registry(self, path: Path) -> dict[str, Any]:
        if not path.exists():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))

    def create_sample(self, payload: SmfpDatasetSampleCreate) -> dict[str, Any]:
        registry = self._load_dataset_registry()
        samples = registry.setdefault("samples", [])
        if payload.label is not None and any(
            sample.get("file_hash") == payload.file_hash and sample.get("label") == payload.label
            for sample in samples
        ):
            raise ValueError("SMFP dataset sample already exists for file_hash + label.")
        now = self._now()
        sample_id = self._sample_id(payload.file_hash, payload.label, now)
        sample = {
            "sample_id": sample_id,
            "file_hash": payload.file_hash,
            "filename": payload.filename,
            "mime_type": payload.mime_type,
            "label": payload.label,
            "split": payload.split,
            "source": payload.source,
            "license": payload.license,
            "feature_schema_version": payload.feature_schema_version,
            "features": payload.features,
            "analyst_notes": payload.analyst_notes,
            "created_at": now,
            "updated_at": now,
        }
        samples.append(sample)
        self._write_dataset_registry(registry)
        return sample

    def list_samples(self) -> dict[str, Any]:
        registry = self._load_dataset_registry()
        return {
            "feature_schema_version": registry.get("feature_schema_version", self.FEATURE_SCHEMA_VERSION),
            "labels": registry.get("labels", []),
            "samples": registry.get("samples", []),
        }

    def dataset_summary(self) -> dict[str, Any]:
        registry = self._load_dataset_registry()
        samples = registry.get("samples", [])
        labels = registry.get("labels", [])
        expected_feature_groups = [
            "identity",
            "metadata_features",
            "origin_heuristic_features",
            "frequency_features",
            "dimensions",
            "mime_type_features",
            "compression_hints",
            "provenance_flags",
        ]

        label_counts: Counter[str] = Counter()
        split_counts: Counter[str] = Counter()
        schema_versions: Counter[str] = Counter()
        missing_feature_counts: Counter[str] = Counter()
        duplicate_index: Counter[tuple[str, str | None]] = Counter()

        for sample in samples:
            label = sample.get("label")
            if label is not None:
                label_counts[str(label)] += 1
            split_counts[str(sample.get("split") or "unassigned")] += 1
            schema_versions[str(sample.get("feature_schema_version") or "unknown")] += 1
            duplicate_index[(str(sample.get("file_hash") or ""), label)] += 1

            features = sample.get("features") or {}
            for group in expected_feature_groups:
                if group not in features or features.get(group) in (None, {}, []):
                    missing_feature_counts[group] += 1

        duplicate_candidates = [
            {"file_hash": file_hash, "label": label, "count": count}
            for (file_hash, label), count in sorted(duplicate_index.items())
            if file_hash and count > 1
        ]
        label_balance_warnings = self._label_balance_warnings(label_counts, labels)
        split_balance_warnings = self._split_balance_warnings(split_counts)

        return {
            "total_samples": len(samples),
            "samples_by_label": {label: label_counts.get(label, 0) for label in labels},
            "samples_by_split": {
                "train": split_counts.get("train", 0),
                "val": split_counts.get("val", 0),
                "test": split_counts.get("test", 0),
                "unassigned": split_counts.get("unassigned", 0),
            },
            "unlabeled_count": sum(1 for sample in samples if sample.get("label") is None),
            "duplicate_candidates": duplicate_candidates,
            "missing_feature_counts": dict(sorted(missing_feature_counts.items())),
            "label_balance_warnings": label_balance_warnings,
            "split_balance_warnings": split_balance_warnings,
            "feature_schema_versions": dict(sorted(schema_versions.items())),
            "ml_status": "dataset_quality_only_no_model",
            "limitations": [
                "Dataset QA does not train or score an ML model",
                "Balance warnings are diagnostics, not model performance metrics",
                "Missing metadata or frequency features may be expected for unsupported media types",
            ],
        }

    def update_sample(self, sample_id: str, payload: SmfpDatasetSampleUpdate) -> dict[str, Any]:
        registry = self._load_dataset_registry()
        samples = registry.setdefault("samples", [])
        for sample in samples:
            if sample.get("sample_id") != sample_id:
                continue
            updates = payload.model_dump(exclude_unset=True)
            new_label = updates.get("label", sample.get("label"))
            if new_label is not None and any(
                other.get("sample_id") != sample_id
                and other.get("file_hash") == sample.get("file_hash")
                and other.get("label") == new_label
                for other in samples
            ):
                raise ValueError("SMFP dataset sample already exists for file_hash + label.")
            sample.update(updates)
            sample["updated_at"] = self._now()
            self._write_dataset_registry(registry)
            return sample
        raise KeyError(f"SMFP dataset sample not found: {sample_id}")

    def _label_balance_warnings(self, label_counts: Counter[str], labels: list[str]) -> list[str]:
        total_labeled = sum(label_counts.values())
        if total_labeled == 0:
            return ["No labeled samples yet."]

        warnings: list[str] = []
        for label in labels:
            if label_counts.get(label, 0) == 0:
                warnings.append(f"Missing label: {label}.")

        dominant_label, dominant_count = label_counts.most_common(1)[0]
        dominant_ratio = dominant_count / total_labeled
        if total_labeled >= 3 and dominant_ratio > 0.7:
            warnings.append(f"Dominant label: {dominant_label} is {dominant_ratio:.0%} of labeled samples.")
        return warnings

    def _split_balance_warnings(self, split_counts: Counter[str]) -> list[str]:
        warnings = [f"Missing split: {split}." for split in ("train", "val", "test") if split_counts.get(split, 0) == 0]
        total_assigned = sum(split_counts.get(split, 0) for split in ("train", "val", "test"))
        if total_assigned == 0:
            warnings.append("No assigned train/val/test samples yet.")
        return warnings

    def _load_dataset_registry(self) -> dict[str, Any]:
        registry = self._load_registry(self.dataset_registry_path)
        registry.setdefault("registry_version", "smfp_dataset_registry_v1")
        registry.setdefault("feature_schema_version", self.FEATURE_SCHEMA_VERSION)
        registry.setdefault(
            "labels",
            [
                "openai_like",
                "midjourney_like",
                "flux_like",
                "stable_diffusion_like",
                "gemini_like",
                "camera_real",
                "unknown",
            ],
        )
        registry.setdefault("datasets", [])
        registry.setdefault("samples", [])
        return registry

    def _write_dataset_registry(self, registry: dict[str, Any]) -> None:
        self.dataset_registry_path.parent.mkdir(parents=True, exist_ok=True)
        self.dataset_registry_path.write_text(
            json.dumps(registry, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    def _sample_id(self, file_hash: str, label: str | None, created_at: str) -> str:
        digest = hashlib.sha256(f"{file_hash}:{label or 'unlabeled'}:{created_at}".encode("utf-8")).hexdigest()
        return f"smfp_sample_{digest[:16]}"

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()
