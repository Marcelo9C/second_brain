import base64
import struct
import unittest
import zlib

import numpy as np

from app.schemas.smfp_frequency import SmfpFrequencyAnalyzeRequest
from app.services.smfp_frequency_service import SmfpFrequencyService


class SmfpFrequencyServiceTest(unittest.TestCase):
    def test_real_like_image_returns_frequency_analysis(self) -> None:
        rng = np.random.default_rng(7)
        image = rng.normal(128, 48, size=(96, 96)).clip(0, 255).astype(np.uint8)

        result = self._analyze(image)

        self.assertEqual(result["analysis_level"], "frequency_heuristic")
        self.assertGreaterEqual(result["camera_likelihood"], 0)
        self.assertTrue(result["signals"])

    def test_ai_like_smooth_periodic_image_has_synthetic_signals(self) -> None:
        y, x = np.indices((128, 128))
        image = (128 + 42 * np.sin(x / 5.0) + 28 * np.cos(y / 7.0)).clip(0, 255).astype(np.uint8)

        result = self._analyze(image)

        self.assertGreater(result["synthetic_likelihood"], 0)
        self.assertTrue(any(signal["matched"] for signal in result["signals"]))

    def test_compressed_blocky_image_is_analyzed_without_absolute_claim(self) -> None:
        base = np.indices((96, 96)).sum(axis=0) % 2
        image = np.kron(base[::8, ::8], np.ones((8, 8)))[:96, :96] * 255

        result = self._analyze(image.astype(np.uint8))

        self.assertEqual(result["analysis_level"], "frequency_heuristic")
        self.assertIn("Frequency forensics is heuristic evidence, not absolute origin proof", result["limitations"])

    def test_image_without_exif_still_returns_frequency_only_limitations(self) -> None:
        image = np.full((64, 64), 128, dtype=np.uint8)

        result = self._analyze(image)

        self.assertEqual(result["analysis_level"], "frequency_heuristic")
        self.assertIn("No ML fingerprint classifier enabled", result["limitations"])

    def _analyze(self, image: np.ndarray) -> dict:
        png = self._png_gray(image)
        return SmfpFrequencyService().analyze(
            SmfpFrequencyAnalyzeRequest(
                filename="sample.png",
                mime_type="image/png",
                content_base64=base64.b64encode(png).decode("ascii"),
            )
        )

    def _png_gray(self, image: np.ndarray) -> bytes:
        height, width = image.shape
        signature = b"\x89PNG\r\n\x1a\n"
        ihdr = struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0)
        raw = b"".join(b"\x00" + image[row].tobytes() for row in range(height))
        return signature + self._chunk(b"IHDR", ihdr) + self._chunk(b"IDAT", zlib.compress(raw)) + self._chunk(b"IEND", b"")

    def _chunk(self, chunk_type: bytes, data: bytes) -> bytes:
        return len(data).to_bytes(4, "big") + chunk_type + data + b"\x00\x00\x00\x00"
