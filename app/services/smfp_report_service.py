from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

from app.schemas.smfp_report import SmfpReportExportRequest
from app.services.smfp_json import canonical_json_bytes
from app.services.smfp_service import SmfpService


class SmfpReportService:
    def __init__(self, *, smfp_service: SmfpService, public_verify_base_url: str) -> None:
        self.smfp_service = smfp_service
        self.public_verify_base_url = public_verify_base_url.rstrip("/")

    def export_json(self, payload: SmfpReportExportRequest) -> dict[str, Any]:
        generated_at = payload.generated_at or datetime.now(timezone.utc).isoformat()
        public_verify_base_url = (payload.public_verify_base_url or self.public_verify_base_url).rstrip("/")

        provenance = payload.provenance_verification
        key_id = provenance.get("key_id")
        key_status = provenance.get("key_status")
        signature_algorithm = provenance.get("signature_algorithm")
        revision_chain_status = "intact" if provenance.get("chain_valid") else "invalid"

        limitations = self._limitations(payload)
        report_body = {
            "asset_id": payload.asset_id,
            "case_id": payload.case_id,
            "filename": payload.filename,
            "mime_type": payload.mime_type,
            "sha256": payload.sha256,
            "timestamp": payload.timestamp,
            "provenance_verification": provenance,
            "key_id": key_id,
            "key_status": key_status,
            "signature_algorithm": signature_algorithm,
            "revision_chain_status": revision_chain_status,
            "origin_analysis": payload.origin_analysis,
            "metadata_signals": payload.metadata_signals,
            "frequency_signals": payload.frequency_signals,
            "evidence_fusion": payload.evidence_fusion,
            "limitations": limitations,
            "analyst_notes": payload.analyst_notes,
            "report_version": payload.report_version,
            "generated_at": generated_at,
            "heuristic_notice": "HEURISTIC ONLY for origin, metadata, frequency, and evidence fusion sections",
        }
        report_hash = self._sha256(self._canonical_bytes(report_body))
        report_id = f"smfp_report_{report_hash[:16]}"
        public_verify_url = f"{public_verify_base_url}/verify.html?report_id={report_id}&asset_id={payload.asset_id or ''}"
        qr_payload = public_verify_url
        report_with_ids = {
            **report_body,
            "report_id": report_id,
            "public_verify_url": public_verify_url,
            "qr_payload": qr_payload,
        }
        report_hash = self._sha256(self._canonical_bytes(report_with_ids))
        report_signature = self.smfp_service._sign(
            {
                "report_hash": report_hash,
                "report_id": report_id,
                "report_version": payload.report_version,
            }
        )
        report = {
            **report_with_ids,
            "report_hash": report_hash,
            "report_signature": report_signature,
            "report_signature_algorithm": self.smfp_service.signature_algorithm,
            "report_key_id": self.smfp_service.signing_key_id,
        }
        canonical_json = self._canonical_bytes(report).decode("utf-8")
        return {
            "report": report,
            "canonical_json": canonical_json,
            "report_id": report_id,
            "report_hash": report_hash,
            "report_signature": report_signature,
            "report_signature_algorithm": self.smfp_service.signature_algorithm,
            "report_key_id": self.smfp_service.signing_key_id,
            "public_verify_url": public_verify_url,
            "qr_payload": qr_payload,
            "format": "json",
            "pdf_available": False,
        }

    def _limitations(self, payload: SmfpReportExportRequest) -> list[str]:
        limitations = list(payload.limitations)
        required = [
            "Exported report signature proves report integrity, not creative origin",
            "Trust score is separate from origin confidence",
            "Origin attribution is probabilistic unless official signed provenance is present",
            "Metadata can be removed or falsified",
            "Frequency signals are heuristic and do not prove AI generation",
            "PDF export is not enabled; JSON is the canonical signed artifact",
        ]
        provenance = payload.provenance_verification or {}
        if provenance.get("key_status") == "revoked":
            required.append("Asset provenance key is revoked; treat the asset verification as high risk")
        for item in required:
            if item not in limitations:
                limitations.append(item)
        return limitations

    def _canonical_bytes(self, payload: dict[str, Any]) -> bytes:
        return canonical_json_bytes(payload)

    def _sha256(self, content: bytes) -> str:
        return hashlib.sha256(content).hexdigest()
