from __future__ import annotations

import importlib.metadata
import importlib.util
import json
import platform
import tempfile
from pathlib import Path
from typing import Any

from app.schemas.smfp_health import SmfpHealthStatus
from app.services.smfp_json import canonical_json_bytes


class SmfpHealthService:
    DEPENDENCIES = {
        "orjson": "orjson",
        "joblib": "joblib",
        "sklearn": "scikit-learn",
        "nacl": "PyNaCl",
        "numpy": "numpy",
    }

    def __init__(
        self,
        *,
        key_registry_path: Path,
        dataset_registry_path: Path,
        model_registry_path: Path,
        model_dir: Path,
    ) -> None:
        self.key_registry_path = key_registry_path
        self.dataset_registry_path = dataset_registry_path
        self.model_registry_path = model_registry_path
        self.model_dir = model_dir

    def check(self) -> SmfpHealthStatus:
        dependencies = self._dependency_status()
        details: dict[str, Any] = {
            "registries": {},
            "paths": {
                "key_registry": str(self.key_registry_path.resolve()),
                "dataset_registry": str(self.dataset_registry_path.resolve()),
                "model_registry": str(self.model_registry_path.resolve()),
                "model_dir": str(self.model_dir.resolve()),
            },
        }

        key_registry = self._registry_status(
            self.key_registry_path,
            expected_container="keys",
            details=details["registries"],
        )
        dataset_registry = self._registry_status(
            self.dataset_registry_path,
            expected_container="samples",
            details=details["registries"],
        )
        model_registry = self._registry_status(
            self.model_registry_path,
            expected_container="models",
            details=details["registries"],
        )
        serialization = self._serialization_status(dependencies)
        path_handling = self._path_status()
        model_artifacts = self._model_artifact_status(details)

        checks = [
            all(item["status"] == "ok" for item in dependencies.values()),
            key_registry == "ok",
            dataset_registry == "ok",
            model_registry == "ok",
            serialization == "ok",
            path_handling == "ok",
            model_artifacts == "ok",
        ]
        return SmfpHealthStatus(
            status="healthy" if all(checks) else "degraded",
            python_version=platform.python_version(),
            dependencies=dependencies,
            key_registry=key_registry,
            dataset_registry=dataset_registry,
            model_registry=model_registry,
            serialization=serialization,
            path_handling=path_handling,
            model_artifacts=model_artifacts,
            details=details,
        )

    def _dependency_status(self) -> dict[str, dict[str, str | None]]:
        result: dict[str, dict[str, str | None]] = {}
        for import_name, package_name in self.DEPENDENCIES.items():
            if importlib.util.find_spec(import_name) is None:
                result[import_name] = {"status": "missing", "version": None}
                continue
            try:
                version = importlib.metadata.version(package_name)
            except importlib.metadata.PackageNotFoundError:
                version = "unknown"
            result[import_name] = {"status": "ok", "version": version}
        return result

    def _registry_status(
        self,
        path: Path,
        *,
        expected_container: str,
        details: dict[str, Any],
    ) -> str:
        name = path.name
        if not path.exists():
            details[name] = {"status": "missing", "path": str(path)}
            return "missing"
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            details[name] = {"status": "corrupted", "error": str(error), "path": str(path)}
            return "corrupted"
        if not isinstance(data, dict) or expected_container not in data:
            details[name] = {"status": "invalid", "path": str(path)}
            return "invalid"
        details[name] = {
            "status": "ok",
            "path": str(path),
            "items": len(data.get(expected_container) or []),
        }
        return "ok"

    def _serialization_status(self, dependencies: dict[str, dict[str, str | None]]) -> str:
        if dependencies.get("joblib", {}).get("status") != "ok":
            return "missing_dependency:joblib"
        try:
            payload = {"encoding": "utf-8", "bytes": "consistent", "value": 1}
            canonical_json_bytes(payload)
            import joblib

            with tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / "smfp_health.joblib"
                joblib.dump(payload, path)
                loaded = joblib.load(path)
            return "ok" if loaded == payload else "roundtrip_failed"
        except Exception as error:  # pragma: no cover - defensive health boundary
            return f"failed:{error.__class__.__name__}"

    def _path_status(self) -> str:
        try:
            for path in (self.key_registry_path, self.dataset_registry_path, self.model_registry_path, self.model_dir):
                path.resolve()
                str(path)
            return "ok"
        except OSError:
            return "failed"

    def _model_artifact_status(self, details: dict[str, Any]) -> str:
        if not self.model_registry_path.exists():
            return "missing_registry"
        try:
            registry = json.loads(self.model_registry_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return "registry_unreadable"
        active_model = registry.get("active_model")
        if not active_model:
            details["model_artifacts"] = {"active_model": None, "status": "disabled"}
            return "ok"
        model_entry = next((item for item in registry.get("models", []) if item.get("model_id") == active_model), None)
        if not model_entry:
            details["model_artifacts"] = {"active_model": active_model, "status": "missing_registry_entry"}
            return "missing_registry_entry"
        model_file = model_entry.get("model_file")
        model_path = self.model_dir / str(model_file)
        if not model_file or not model_path.exists():
            details["model_artifacts"] = {"active_model": active_model, "status": "missing_artifact"}
            return "missing_artifact"
        details["model_artifacts"] = {"active_model": active_model, "status": "ok", "path": str(model_path)}
        return "ok"
