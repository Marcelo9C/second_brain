import unittest

from app.schemas.smfp_evidence_fusion import SmfpEvidenceFusionRequest
from app.services.smfp_evidence_fusion_service import SmfpEvidenceFusionService


class SmfpEvidenceFusionServiceTest(unittest.TestCase):
    def test_verified_synthetic_like_keeps_scores_separate(self) -> None:
        result = SmfpEvidenceFusionService().fuse(
            SmfpEvidenceFusionRequest(
                provenance={
                    "content_hash_valid": True,
                    "signature_valid": True,
                    "chain_valid": True,
                    "key_status": "active",
                    "tampering": "none",
                    "audit_report": {"trust": {"trust_score": 100}},
                },
                origin_analysis={
                    "likely_producer": "openai_like",
                    "confidence": 0.41,
                    "synthetic_media_likelihood": 0.41,
                },
                frequency_analysis={
                    "synthetic_likelihood": 0.52,
                    "signals": [{"label": "spectral anomaly", "matched": True}],
                },
            )
        )

        self.assertEqual(result["overall_assessment"], "verified_synthetic_like")
        self.assertEqual(result["origin_confidence"], 0.41)
        self.assertEqual(result["synthetic_likelihood"], 0.52)
        self.assertIn("Evidence fusion does not modify cryptographic trust_score", result["limitations"])

    def test_invalid_signature_never_becomes_verified(self) -> None:
        result = SmfpEvidenceFusionService().fuse(
            SmfpEvidenceFusionRequest(
                provenance={
                    "content_hash_valid": True,
                    "signature_valid": False,
                    "chain_valid": True,
                    "key_status": "active",
                    "tampering": "none",
                },
                origin_analysis={
                    "likely_producer": "openai_like",
                    "confidence": 0.58,
                    "synthetic_media_likelihood": 0.58,
                },
            )
        )

        self.assertEqual(result["overall_assessment"], "unverified_synthetic_like")
        self.assertTrue(any("Signature invalid" in item for item in result["explainability"]))

    def test_tampered_assessment_wins(self) -> None:
        result = SmfpEvidenceFusionService().fuse(
            SmfpEvidenceFusionRequest(
                provenance={
                    "content_hash_valid": False,
                    "signature_valid": True,
                    "chain_valid": True,
                    "key_status": "active",
                    "tampering": "suspected",
                },
                frequency_analysis={"synthetic_likelihood": 0.7},
            )
        )

        self.assertEqual(result["overall_assessment"], "tampered")
