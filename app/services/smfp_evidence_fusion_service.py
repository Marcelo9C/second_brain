from __future__ import annotations

from typing import Any

from app.schemas.smfp_evidence_fusion import SmfpEvidenceFusionRequest


class SmfpEvidenceFusionService:
    def fuse(self, payload: SmfpEvidenceFusionRequest) -> dict[str, Any]:
        provenance = payload.provenance or {}
        origin = payload.origin_analysis or {}
        frequency = payload.frequency_analysis or {}

        content_hash_valid = bool(provenance.get("content_hash_valid"))
        signature_valid = bool(provenance.get("signature_valid"))
        chain_valid = bool(provenance.get("chain_valid"))
        tampering = str(provenance.get("tampering") or provenance.get("audit_report", {}).get("trust", {}).get("tampering", "unknown"))
        key_status = str(provenance.get("key_status", "unknown"))
        provenance_valid = content_hash_valid and signature_valid and chain_valid and key_status != "revoked"

        origin_confidence = self._clamp(origin.get("confidence", 0.0))
        origin_producer = str(origin.get("likely_producer", "unknown"))
        origin_synthetic = self._clamp(origin.get("synthetic_media_likelihood", 0.0))
        frequency_synthetic = self._clamp(frequency.get("synthetic_likelihood", 0.0))
        synthetic_likelihood = max(origin_synthetic, frequency_synthetic)
        synthetic_like = synthetic_likelihood >= 0.35 or (origin_producer != "unknown" and origin_confidence >= 0.25)

        if tampering == "suspected" or not content_hash_valid:
            assessment = "tampered"
        elif provenance_valid and synthetic_like:
            assessment = "verified_synthetic_like"
        elif provenance_valid:
            assessment = "verified_unknown"
        elif synthetic_like:
            assessment = "unverified_synthetic_like"
        else:
            assessment = "unknown"

        evidence_summary = self._evidence_summary(
            provenance=provenance,
            origin=origin,
            frequency=frequency,
            provenance_valid=provenance_valid,
            synthetic_like=synthetic_like,
        )

        limitations = [
            "Evidence fusion does not modify cryptographic trust_score",
            "Valid provenance proves integrity and signing status, not creative origin",
            "Origin confidence is probabilistic and separate from trust_score",
            "Frequency anomaly is heuristic evidence and does not prove AI generation",
            "Metadata can be removed or falsified",
            "No ML fingerprint classifier enabled",
        ]

        explainability = [
            f"Provenance valid: {provenance_valid}",
            f"Key status: {key_status}",
            f"Origin producer hint: {origin_producer}",
            f"Origin confidence retained separately: {origin_confidence:.2f}",
            f"Synthetic likelihood retained separately: {synthetic_likelihood:.2f}",
            "Signature invalid or hash mismatch never increases trust",
        ]

        return {
            "overall_assessment": assessment,
            "origin_confidence": round(origin_confidence, 2),
            "synthetic_likelihood": round(synthetic_likelihood, 2),
            "evidence_summary": evidence_summary,
            "limitations": limitations,
            "explainability": explainability,
        }

    def _evidence_summary(
        self,
        *,
        provenance: dict[str, Any],
        origin: dict[str, Any],
        frequency: dict[str, Any],
        provenance_valid: bool,
        synthetic_like: bool,
    ) -> list[str]:
        summary = [
            "Provenance verification passed" if provenance_valid else "Provenance verification did not fully pass",
            f"Content hash valid: {bool(provenance.get('content_hash_valid'))}",
            f"Ed25519 signature valid: {bool(provenance.get('signature_valid'))}",
            f"Revision chain intact: {bool(provenance.get('chain_valid'))}",
        ]
        producer = origin.get("likely_producer", "unknown")
        if producer != "unknown":
            summary.append(f"Origin analysis suggests {producer}")
        else:
            summary.append("Origin analysis did not identify a producer family")
        summary.append("Synthetic-like evidence present" if synthetic_like else "Synthetic-like evidence is weak or absent")

        matched_frequency = [
            signal.get("label", signal.get("type", "frequency signal"))
            for signal in frequency.get("signals", [])
            if signal.get("matched")
        ]
        if matched_frequency:
            summary.append("Frequency signals: " + ", ".join(str(item) for item in matched_frequency[:3]))
        return summary

    def _clamp(self, value: Any) -> float:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return 0.0
        return min(max(number, 0.0), 1.0)
