import base64
import tempfile
import unittest
from pathlib import Path

import orjson
from nacl.signing import VerifyKey

from app.schemas.smfp_report import SmfpReportExportRequest
from app.services.smfp_report_service import SmfpReportService
from app.services.smfp_service import SmfpService


class SmfpReportServiceTest(unittest.TestCase):
    def test_export_report_json_is_deterministic_and_signed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            seed = bytes.fromhex("88" * 32)
            smfp_service = SmfpService(
                storage_dir=Path(tmp),
                signing_secret="unit-secret",
                key_id="report-key",
                private_key=seed.hex(),
            )
            service = SmfpReportService(
                smfp_service=smfp_service,
                public_verify_base_url="http://127.0.0.1:8765",
            )
            payload = self._payload(generated_at="2026-05-15T20:00:00+00:00")

            first = service.export_json(payload)
            second = service.export_json(payload)

            self.assertEqual(first["report_hash"], second["report_hash"])
            self.assertEqual(first["canonical_json"], second["canonical_json"])
            self.assertEqual(first["report"]["report_id"], first["report_id"])
            self.assertIn("public_verify_url", first["report"])
            self.assertIn("limitations", first["report"])
            self.assertFalse(first["pdf_available"])

            signed_payload = {
                "report_hash": first["report_hash"],
                "report_id": first["report_id"],
                "report_version": "SMFP v1.6",
            }
            VerifyKey(base64.b64decode(smfp_service.active_public_key)).verify(
                orjson.dumps(signed_payload, option=orjson.OPT_SORT_KEYS),
                base64.b64decode(first["report_signature"]),
            )

    def test_revoked_asset_key_is_preserved_as_risk(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            smfp_service = SmfpService(
                storage_dir=Path(tmp),
                signing_secret="unit-secret",
                key_id="report-key",
            )
            service = SmfpReportService(
                smfp_service=smfp_service,
                public_verify_base_url="http://127.0.0.1:8765",
            )
            payload = self._payload(generated_at="2026-05-15T20:00:00+00:00")
            payload.provenance_verification["key_status"] = "revoked"

            result = service.export_json(payload)

            self.assertEqual(result["report"]["key_status"], "revoked")
            self.assertTrue(
                any("revoked" in limitation for limitation in result["report"]["limitations"])
            )

    def _payload(self, *, generated_at: str) -> SmfpReportExportRequest:
        return SmfpReportExportRequest(
            asset_id="smfp_unit",
            case_id="case-001",
            filename="evidence.png",
            mime_type="image/png",
            sha256="a" * 64,
            timestamp="2026-05-15T19:59:00+00:00",
            generated_at=generated_at,
            provenance_verification={
                "content_hash_valid": True,
                "signature_valid": True,
                "key_id": "asset-key",
                "key_status": "active",
                "signature_algorithm": "Ed25519",
                "chain_valid": True,
                "tampering": "none",
                "audit_report": {"trust": {"trust_score": 100}},
            },
            origin_analysis={
                "likely_producer": "openai_like",
                "confidence": 0.41,
                "attribution_level": "heuristic",
            },
            metadata_signals=[
                {
                    "type": "filename_signal",
                    "label": "filename contains ChatGPT Image",
                    "matched": True,
                    "weight": 0.35,
                }
            ],
            frequency_signals=[
                {
                    "type": "spectral_anomaly",
                    "label": "spectral anomaly",
                    "matched": True,
                    "weight": 0.22,
                }
            ],
            evidence_fusion={
                "overall_assessment": "verified_synthetic_like",
                "origin_confidence": 0.41,
                "synthetic_likelihood": 0.52,
            },
            limitations=["No ML fingerprint classifier enabled"],
            analyst_notes="Reviewed by unit test.",
        )
