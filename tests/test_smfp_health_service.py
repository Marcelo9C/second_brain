import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.services.smfp_health_service import SmfpHealthService


class SmfpHealthServiceTest(unittest.TestCase):
    def test_health_is_healthy_with_valid_environment(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = self._service(tmp)

            result = service.check().model_dump()

            self.assertEqual(result["status"], "healthy")
            self.assertEqual(result["key_registry"], "ok")
            self.assertEqual(result["dataset_registry"], "ok")
            self.assertEqual(result["model_registry"], "ok")
            self.assertEqual(result["serialization"], "ok")
            self.assertIn("orjson", result["dependencies"])

    def test_missing_registry_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = self._service(tmp, write_dataset=False)

            result = service.check().model_dump()

            self.assertEqual(result["status"], "degraded")
            self.assertEqual(result["dataset_registry"], "missing")

    def test_corrupted_registry_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = self._service(tmp)
            (Path(tmp) / "dataset_registry.json").write_text("{not-json", encoding="utf-8")

            result = service.check().model_dump()

            self.assertEqual(result["status"], "degraded")
            self.assertEqual(result["dataset_registry"], "corrupted")

    def test_missing_orjson_is_reported(self) -> None:
        self._assert_missing_dependency("orjson")

    def test_missing_sklearn_is_reported(self) -> None:
        self._assert_missing_dependency("sklearn")

    def test_missing_joblib_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = self._service(tmp)

            with patch("app.services.smfp_health_service.importlib.util.find_spec") as find_spec:
                find_spec.side_effect = lambda name: None if name == "joblib" else object()
                result = service.check().model_dump()

            self.assertEqual(result["status"], "degraded")
            self.assertEqual(result["dependencies"]["joblib"]["status"], "missing")
            self.assertEqual(result["serialization"], "missing_dependency:joblib")

    def _assert_missing_dependency(self, dependency: str) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = self._service(tmp)

            with patch("app.services.smfp_health_service.importlib.util.find_spec") as find_spec:
                find_spec.side_effect = lambda name: None if name == dependency else object()
                result = service.check().model_dump()

            self.assertEqual(result["status"], "degraded")
            self.assertEqual(result["dependencies"][dependency]["status"], "missing")

    def _service(self, tmp: str, *, write_dataset: bool = True) -> SmfpHealthService:
        root = Path(tmp)
        key_registry = root / "key_registry.json"
        dataset_registry = root / "dataset_registry.json"
        model_registry = root / "model_registry.json"
        key_registry.write_text(
            json.dumps({"keys": [{"key_id": "health-key", "status": "active"}]}),
            encoding="utf-8",
        )
        if write_dataset:
            dataset_registry.write_text(
                json.dumps({"registry_version": "test_dataset", "samples": []}),
                encoding="utf-8",
            )
        model_registry.write_text(
            json.dumps({"registry_version": "test_model", "models": [], "active_model": None}),
            encoding="utf-8",
        )
        return SmfpHealthService(
            key_registry_path=key_registry,
            dataset_registry_path=dataset_registry,
            model_registry_path=model_registry,
            model_dir=root,
        )
