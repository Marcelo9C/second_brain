import base64
import struct
import unittest

from app.schemas.smfp_metadata import SmfpMetadataExtractRequest
from app.schemas.smfp_origin import SmfpOriginAnalyzeRequest
from app.services.smfp_metadata_service import SmfpMetadataService
from app.services.smfp_origin_service import SmfpOriginService


class SmfpMetadataServiceTest(unittest.TestCase):
    def test_png_text_chunk_chatgpt_returns_openai_like_signal(self) -> None:
        png = self._png_with_text("Software", "ChatGPT Image")
        service = SmfpMetadataService()

        result = service.extract(
            SmfpMetadataExtractRequest(
                filename="generic.png",
                mime_type="image/png",
                content_base64=base64.b64encode(png).decode("ascii"),
            )
        )

        self.assertTrue(result["extracted"]["png_chunks"])
        self.assertTrue(
            any(signal["producer_hint"] == "openai_like" and signal["matched"] for signal in result["signals"])
        )

        origin = SmfpOriginService(metadata_service=service).analyze(
            SmfpOriginAnalyzeRequest(
                filename="generic.png",
                mime_type="image/png",
                content_base64=base64.b64encode(png).decode("ascii"),
            )
        )
        self.assertEqual(origin["likely_producer"], "openai_like")
        self.assertGreater(origin["confidence"], 0)
        self.assertTrue(origin["metadata_signals"])

    def test_generic_filename_without_metadata_returns_unknown_with_absence_limitation(self) -> None:
        service = SmfpMetadataService()

        result = service.extract(
            SmfpMetadataExtractRequest(
                filename="generic.bin",
                mime_type="application/octet-stream",
                content_base64=base64.b64encode(b"plain bytes").decode("ascii"),
            )
        )

        self.assertIn("No embedded metadata detected in the provided sample", result["limitations"])

        origin = SmfpOriginService(metadata_service=service).analyze(
            SmfpOriginAnalyzeRequest(
                filename="generic.bin",
                mime_type="application/octet-stream",
                content_base64=base64.b64encode(b"plain bytes").decode("ascii"),
            )
        )
        self.assertEqual(origin["likely_producer"], "unknown")
        self.assertEqual(origin["confidence"], 0)

    def test_pdf_metadata_is_extracted_when_available(self) -> None:
        pdf = (
            b"%PDF-1.4\n"
            b"1 0 obj << /Title (Forensic Sample) /Creator (ComfyUI) /Producer (Stable Diffusion) >> endobj\n"
            b"%%EOF"
        )
        service = SmfpMetadataService()

        result = service.extract(
            SmfpMetadataExtractRequest(
                filename="sample.pdf",
                mime_type="application/pdf",
                content_base64=base64.b64encode(pdf).decode("ascii"),
            )
        )

        self.assertEqual(result["extracted"]["pdf_metadata"]["Title"], "Forensic Sample")
        self.assertEqual(result["extracted"]["pdf_metadata"]["Creator"], "ComfyUI")
        self.assertTrue(
            any(signal["producer_hint"] == "stable_diffusion_like" for signal in result["signals"])
        )

    def _png_with_text(self, keyword: str, text: str) -> bytes:
        signature = b"\x89PNG\r\n\x1a\n"
        ihdr_data = struct.pack(">IIBBBBB", 1024, 1024, 8, 2, 0, 0, 0)
        text_data = f"{keyword}\x00{text}".encode("utf-8")
        return (
            signature
            + self._chunk(b"IHDR", ihdr_data)
            + self._chunk(b"tEXt", text_data)
            + self._chunk(b"IEND", b"")
        )

    def _chunk(self, chunk_type: bytes, data: bytes) -> bytes:
        return len(data).to_bytes(4, "big") + chunk_type + data + b"\x00\x00\x00\x00"
