import unittest

from app.schemas.smfp_origin import SmfpOriginAnalyzeRequest
from app.services.smfp_origin_service import SmfpOriginService


class SmfpOriginServiceTest(unittest.TestCase):
    def test_chatgpt_image_filename_returns_openai_like_with_moderate_confidence(self) -> None:
        service = SmfpOriginService()

        result = service.analyze(
            SmfpOriginAnalyzeRequest(
                filename="ChatGPT Image 15 de mai.png",
                mime_type="image/png",
                content_hash="abc123",
            )
        )

        self.assertEqual(result["likely_producer"], "openai_like")
        self.assertGreater(result["confidence"], 0)
        self.assertLessEqual(result["confidence"], 0.41)
        self.assertEqual(result["attribution_level"], "heuristic")
        self.assertIn("No ML fingerprint classifier enabled", result["limitations"])
        self.assertTrue(
            any(
                evidence["type"] == "filename_signal"
                and evidence["matched"]
                and "ChatGPT Image" in evidence["label"]
                for evidence in result["evidence"]
            )
        )

    def test_generic_filename_returns_unknown(self) -> None:
        service = SmfpOriginService()

        result = service.analyze(
            SmfpOriginAnalyzeRequest(
                filename="evidence.png",
                mime_type="image/png",
                content_hash="abc123",
            )
        )

        self.assertEqual(result["likely_producer"], "unknown")
        self.assertEqual(result["confidence"], 0)
