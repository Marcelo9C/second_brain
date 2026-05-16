from __future__ import annotations

from collections import defaultdict
from typing import Any

from app.schemas.smfp_metadata import SmfpMetadataExtractRequest
from app.schemas.smfp_origin import SmfpOriginAnalyzeRequest
from app.services.smfp_metadata_service import SmfpMetadataService


class SmfpOriginService:
    def __init__(self, metadata_service: SmfpMetadataService | None = None) -> None:
        self.metadata_service = metadata_service or SmfpMetadataService()

    def analyze(self, payload: SmfpOriginAnalyzeRequest) -> dict[str, Any]:
        evidence: list[dict[str, Any]] = []
        producer_scores: defaultdict[str, float] = defaultdict(float)
        synthetic_score = 0.0

        filename = payload.filename.lower()
        metadata_result = self.metadata_service.extract(
            SmfpMetadataExtractRequest(
                filename=payload.filename,
                mime_type=payload.mime_type,
                content_base64=payload.content_base64,
                metadata=payload.metadata,
            )
        )

        self._add_filename_signal(
            evidence,
            producer_scores,
            filename=filename,
            needle="chatgpt image",
            label='filename contains "ChatGPT Image"',
            producer="openai_like",
            weight=0.35,
        )
        self._add_filename_signal(
            evidence,
            producer_scores,
            filename=filename,
            needle="dall-e",
            label='filename contains "DALL-E"',
            producer="openai_like",
            weight=0.35,
        )
        self._add_filename_signal(
            evidence,
            producer_scores,
            filename=filename,
            needle="midjourney",
            label='filename contains "Midjourney"',
            producer="midjourney_like",
            weight=0.35,
        )
        self._add_filename_signal(
            evidence,
            producer_scores,
            filename=filename,
            needle="mj",
            label='filename contains "mj"',
            producer="midjourney_like",
            weight=0.18,
            require_token=True,
        )
        self._add_filename_signal(
            evidence,
            producer_scores,
            filename=filename,
            needle="flux",
            label='filename contains "Flux"',
            producer="flux_like",
            weight=0.35,
        )
        for needle in ["stable diffusion", "comfyui", "automatic1111"]:
            self._add_filename_signal(
                evidence,
                producer_scores,
                filename=filename,
                needle=needle,
                label=f'filename contains "{needle}"',
                producer="stable_diffusion_like",
                weight=0.35,
            )

        for signal in metadata_result["signals"]:
            evidence.append(
                {
                    "type": signal["type"],
                    "label": signal["label"],
                    "weight": signal["weight"],
                    "matched": signal["matched"],
                }
            )
            if signal["matched"]:
                producer_hint = signal.get("producer_hint", "unknown")
                if producer_hint != "unknown":
                    producer_scores[producer_hint] += float(signal["weight"])
                else:
                    synthetic_score += min(float(signal["weight"]), 0.18)

        if payload.manifest:
            evidence.append(
                {
                    "type": "provenance_manifest",
                    "label": "SMFP provenance manifest provided",
                    "weight": 0.18,
                    "matched": True,
                }
            )
            synthetic_score += 0.18

        likely_producer = "unknown"
        confidence = 0.0
        if producer_scores:
            likely_producer, confidence = max(producer_scores.items(), key=lambda item: item[1])
            confidence = min(confidence, 0.58)
            if self._only_filename_evidence(evidence):
                confidence = min(confidence, 0.41)

        synthetic_media_likelihood = min(max(confidence, synthetic_score), 0.92)
        if likely_producer == "unknown":
            synthetic_media_likelihood = min(synthetic_media_likelihood, 0.28)

        self._add_unmatched_baselines(evidence)

        return {
            "synthetic_media_likelihood": round(synthetic_media_likelihood, 2),
            "likely_producer": likely_producer,
            "confidence": round(confidence, 2),
            "evidence": evidence,
            "metadata": metadata_result["extracted"],
            "metadata_signals": metadata_result["signals"],
            "limitations": metadata_result["limitations"] + [
                "No official C2PA provenance detected",
                "No ML fingerprint classifier enabled",
                "Origin attribution is probabilistic and must not be treated as absolute origin proof",
            ],
            "attribution_level": "heuristic",
        }

    def _add_filename_signal(
        self,
        evidence: list[dict[str, Any]],
        producer_scores: defaultdict[str, float],
        *,
        filename: str,
        needle: str,
        label: str,
        producer: str,
        weight: float,
        require_token: bool = False,
    ) -> None:
        matched = f" {needle} " in f" {filename.replace('_', ' ').replace('-', ' ')} " if require_token else needle in filename
        if not matched:
            return
        evidence.append(
            {
                "type": "filename_signal",
                "label": label,
                "weight": weight,
                "matched": True,
            }
        )
        producer_scores[producer] += weight

    def _only_filename_evidence(self, evidence: list[dict[str, Any]]) -> bool:
        matched = [item for item in evidence if item["matched"] and item["type"] != "metadata_absence_signal"]
        return bool(matched) and all(item["type"] == "filename_signal" for item in matched)

    def _add_unmatched_baselines(self, evidence: list[dict[str, Any]]) -> None:
        labels = {item["label"] for item in evidence}
        baselines = [
            ("official_provenance", "no official provenance", 0.0),
            ("ml_classifier", "no ML fingerprint classifier yet", 0.0),
        ]
        for evidence_type, label, weight in baselines:
            if label not in labels:
                evidence.append(
                    {
                        "type": evidence_type,
                        "label": label,
                        "weight": weight,
                        "matched": False,
                    }
                )
