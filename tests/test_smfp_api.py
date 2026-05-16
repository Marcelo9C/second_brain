import tempfile
import unittest
import base64
import struct
import zlib
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.services.smfp_inference_service import SmfpInferenceService
from app.services.smfp_ml_service import SmfpMlService
from app.services.smfp_service import SmfpService


class SmfpApiTest(unittest.TestCase):
    def test_public_key_and_manifest_export_endpoints(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ml_service = SmfpMlService(
                dataset_registry_path=Path(tmp) / "dataset_registry.json",
                model_registry_path=Path(tmp) / "model_registry.json",
            )
            inference_service = SmfpInferenceService(
                ml_service=ml_service,
                model_registry_path=Path(tmp) / "model_registry.json",
                model_dir=Path(tmp),
            )
            service = SmfpService(
                storage_dir=Path(tmp),
                signing_secret="api-secret",
                key_id="api-key",
            )

            with (
                patch("app.api.routes.smfp.get_smfp_service", return_value=service),
                patch("app.api.routes.smfp.get_smfp_ml_service", return_value=ml_service),
                patch("app.api.routes.smfp.get_smfp_inference_service", return_value=inference_service),
            ):
                client = TestClient(app)
                created = client.post(
                    "/api/smfp/assets",
                    json={
                        "filename": "evidence.txt",
                        "mime_type": "text/plain",
                        "content_text": "API evidence.",
                    },
                )
                self.assertEqual(created.status_code, 200)
                asset_id = created.json()["asset_id"]

                public_key = client.get("/api/smfp/public-keys/api-key")
                self.assertEqual(public_key.status_code, 200)
                self.assertEqual(public_key.json()["signature_algorithm"], "Ed25519")
                self.assertEqual(public_key.json()["status"], "active")

                public_keys = client.get("/api/smfp/public-keys")
                self.assertEqual(public_keys.status_code, 200)
                self.assertEqual(public_keys.json()["keys"][0]["key_id"], "api-key")

                exported = client.get(f"/api/smfp/assets/{asset_id}/manifest/export")
                self.assertEqual(exported.status_code, 200)
                self.assertEqual(exported.json()["filename"], f"{asset_id}.manifest.json")
                self.assertEqual(exported.json()["manifest"]["signature_mode"], "PUBLIC_ED25519")

                verification = client.get(f"/api/smfp/assets/{asset_id}/verify")
                self.assertEqual(verification.status_code, 200)
                self.assertTrue(verification.json()["signature_valid"])

                public_verification = client.post(
                    "/api/smfp/verify",
                    json={
                        "content_text": "API evidence.",
                        "manifest": exported.json()["manifest"],
                    },
                )
                self.assertEqual(public_verification.status_code, 200)
                self.assertTrue(public_verification.json()["content_hash_valid"])
                self.assertTrue(public_verification.json()["signature_valid"])
                self.assertEqual(public_verification.json()["key_status"], "active")

                origin = client.post(
                    "/api/smfp/origin/analyze",
                    json={
                        "filename": "ChatGPT Image 15 de mai.png",
                        "mime_type": "image/png",
                        "content_hash": exported.json()["manifest"]["content_hash"],
                        "manifest": exported.json()["manifest"],
                    },
                )
                self.assertEqual(origin.status_code, 200)
                self.assertEqual(origin.json()["likely_producer"], "openai_like")
                self.assertEqual(origin.json()["attribution_level"], "heuristic")

                metadata = client.post(
                    "/api/smfp/metadata/extract",
                    json={
                        "filename": "evidence.txt",
                        "mime_type": "text/plain",
                        "content_base64": "ZXZpZGVuY2U=",
                    },
                )
                self.assertEqual(metadata.status_code, 200)
                self.assertIn("extracted", metadata.json())
                self.assertIn("limitations", metadata.json())

                frequency = client.post(
                    "/api/smfp/frequency/analyze",
                    json={
                        "filename": "sample.png",
                        "mime_type": "image/png",
                        "content_base64": base64.b64encode(_png_gray()).decode("ascii"),
                    },
                )
                self.assertEqual(frequency.status_code, 200)
                self.assertEqual(frequency.json()["analysis_level"], "frequency_heuristic")
                self.assertIn("signals", frequency.json())

                fusion = client.post(
                    "/api/smfp/evidence/fuse",
                    json={
                        "provenance": public_verification.json(),
                        "origin_analysis": origin.json(),
                        "frequency_analysis": frequency.json(),
                    },
                )
                self.assertEqual(fusion.status_code, 200)
                self.assertIn("overall_assessment", fusion.json())
                self.assertIn("origin_confidence", fusion.json())
                self.assertIn("synthetic_likelihood", fusion.json())

                report = client.post(
                    "/api/smfp/reports/export",
                    json={
                        "asset_id": asset_id,
                        "case_id": "api-case",
                        "filename": "evidence.txt",
                        "mime_type": "text/plain",
                        "sha256": exported.json()["manifest"]["content_hash"],
                        "timestamp": "2026-05-15T20:00:00+00:00",
                        "generated_at": "2026-05-15T20:01:00+00:00",
                        "provenance_verification": public_verification.json(),
                        "origin_analysis": origin.json(),
                        "metadata_signals": origin.json().get("metadata_signals", []),
                        "frequency_signals": frequency.json().get("signals", []),
                        "evidence_fusion": fusion.json(),
                        "limitations": fusion.json().get("limitations", []),
                        "analyst_notes": "API export test.",
                    },
                )
                self.assertEqual(report.status_code, 200)
                self.assertIn("report_id", report.json())
                self.assertIn("report_hash", report.json())
                self.assertIn("report_signature", report.json())
                self.assertIn("public_verify_url", report.json())

                features = client.post(
                    "/api/smfp/ml/features/export",
                    json={
                        "filename": "evidence.txt",
                        "mime_type": "text/plain",
                        "content_hash": exported.json()["manifest"]["content_hash"],
                        "metadata_extraction": metadata.json(),
                        "origin_analysis": origin.json(),
                        "frequency_analysis": frequency.json(),
                        "provenance_verification": public_verification.json(),
                        "manifest": exported.json()["manifest"],
                    },
                )
                self.assertEqual(features.status_code, 200)
                self.assertEqual(features.json()["ml_status"], "features_only_no_model")
                self.assertEqual(features.json()["ml_classifier"], "disabled")
                self.assertNotIn("ml_probability", features.json())

                inference = client.post(
                    "/api/smfp/ml/infer",
                    json={
                        "filename": "evidence.txt",
                        "mime_type": "text/plain",
                        "content_hash": exported.json()["manifest"]["content_hash"],
                        "metadata_extraction": metadata.json(),
                        "origin_analysis": origin.json(),
                        "frequency_analysis": frequency.json(),
                        "provenance_verification": public_verification.json(),
                        "manifest": exported.json()["manifest"],
                    },
                )
                self.assertEqual(inference.status_code, 200)
                self.assertEqual(inference.json()["ml_status"], "disabled")
                self.assertEqual(inference.json()["predictions"], [])

                sample = client.post(
                    "/api/smfp/dataset/samples",
                    json={
                        "file_hash": exported.json()["manifest"]["content_hash"],
                        "filename": "evidence.txt",
                        "mime_type": "text/plain",
                        "label": "openai_like",
                        "split": "train",
                        "source": "lab",
                        "license": "internal-review",
                        "feature_schema_version": features.json()["feature_schema_version"],
                        "features": features.json()["features"],
                        "analyst_notes": "API dataset sample test.",
                    },
                )
                self.assertEqual(sample.status_code, 200)
                sample_id = sample.json()["sample_id"]

                duplicate = client.post(
                    "/api/smfp/dataset/samples",
                    json={
                        "file_hash": exported.json()["manifest"]["content_hash"],
                        "label": "openai_like",
                    },
                )
                self.assertEqual(duplicate.status_code, 409)

                invalid = client.post(
                    "/api/smfp/dataset/samples",
                    json={
                        "file_hash": "invalid-label-hash",
                        "label": "invalid_label",
                    },
                )
                self.assertEqual(invalid.status_code, 422)

                samples = client.get("/api/smfp/dataset/samples")
                self.assertEqual(samples.status_code, 200)
                self.assertTrue(any(item["sample_id"] == sample_id for item in samples.json()["samples"]))

                summary = client.get("/api/smfp/dataset/summary")
                self.assertEqual(summary.status_code, 200)
                self.assertEqual(summary.json()["total_samples"], 1)
                self.assertEqual(summary.json()["samples_by_label"]["openai_like"], 1)
                self.assertEqual(summary.json()["samples_by_split"]["train"], 1)
                self.assertEqual(summary.json()["ml_status"], "dataset_quality_only_no_model")

                health = client.get("/api/smfp/health")
                self.assertEqual(health.status_code, 200)
                self.assertIn(health.json()["status"], {"healthy", "degraded"})
                self.assertIn("python_version", health.json())
                self.assertIn("dependencies", health.json())
                self.assertIn("key_registry", health.json())
                self.assertIn("dataset_registry", health.json())
                self.assertIn("model_registry", health.json())
                self.assertIn("serialization", health.json())

                updated = client.patch(
                    f"/api/smfp/dataset/samples/{sample_id}",
                    json={"label": "camera_real", "split": "val"},
                )
                self.assertEqual(updated.status_code, 200)
                self.assertEqual(updated.json()["label"], "camera_real")
                self.assertEqual(updated.json()["split"], "val")

                public_page = client.get("/verify.html")
                self.assertEqual(public_page.status_code, 200)
                self.assertNotIn("session_orchestrator", public_page.text)


def _png_gray() -> bytes:
    width = height = 16
    signature = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0)
    row = bytes(range(16))
    raw = b"".join(b"\x00" + row for _ in range(height))
    return signature + _chunk(b"IHDR", ihdr) + _chunk(b"IDAT", zlib.compress(raw)) + _chunk(b"IEND", b"")


def _chunk(chunk_type: bytes, data: bytes) -> bytes:
    return len(data).to_bytes(4, "big") + chunk_type + data + b"\x00\x00\x00\x00"
