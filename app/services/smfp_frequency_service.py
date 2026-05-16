from __future__ import annotations

import base64
import struct
import zlib
from typing import Any

import numpy as np

from app.schemas.smfp_frequency import SmfpFrequencyAnalyzeRequest


class SmfpFrequencyService:
    def analyze(self, payload: SmfpFrequencyAnalyzeRequest) -> dict[str, Any]:
        limitations = [
            "Frequency forensics is heuristic evidence, not absolute origin proof",
            "Compression, resizing, screenshots, and post-processing can distort frequency signals",
            "Frequency signals do not replace provenance verification or origin analysis",
            "No ML fingerprint classifier enabled",
        ]
        image = self._decode_image(payload.content_base64, payload.mime_type)
        if image is None:
            return {
                "synthetic_likelihood": 0.0,
                "camera_likelihood": 0.0,
                "signals": [],
                "limitations": limitations + ["Image format could not be decoded by the lightweight frequency analyzer"],
                "analysis_level": "frequency_heuristic",
            }

        image = self._resize_for_analysis(image)
        features = self._features(image)
        signals = self._signals(features)
        synthetic_score = sum(signal["weight"] for signal in signals if signal["matched"])
        synthetic_likelihood = min(max(synthetic_score, 0.0), 0.88)
        camera_likelihood = min(max(1.0 - synthetic_likelihood - self._camera_penalty(features), 0.0), 1.0)

        return {
            "synthetic_likelihood": round(synthetic_likelihood, 2),
            "camera_likelihood": round(camera_likelihood, 2),
            "signals": signals,
            "limitations": limitations,
            "analysis_level": "frequency_heuristic",
        }

    def _features(self, image: np.ndarray) -> dict[str, float]:
        centered = image - float(np.mean(image))
        fft = np.fft.fftshift(np.fft.fft2(centered))
        magnitude = np.log1p(np.abs(fft))
        height, width = image.shape
        yy, xx = np.indices((height, width))
        cy, cx = height // 2, width // 2
        radius = np.sqrt((yy - cy) ** 2 + (xx - cx) ** 2)
        max_radius = float(radius.max() or 1.0)
        low_mask = radius <= max_radius * 0.18
        high_mask = radius >= max_radius * 0.62
        mid_mask = (radius > max_radius * 0.18) & (radius < max_radius * 0.62)

        high_energy = float(np.mean(magnitude[high_mask]) / (np.mean(magnitude) + 1e-9))
        low_ratio = float(np.mean(magnitude[low_mask]) / (np.mean(magnitude[mid_mask]) + 1e-9))

        blur = self._box_blur(image)
        residual = image - blur
        noise_residual = float(np.std(residual) / 255.0)

        gx = np.diff(image, axis=1)
        gy = np.diff(image, axis=0)
        edge_strength = np.sqrt(gx[:-1, :] ** 2 + gy[:, :-1] ** 2)
        edge_consistency = float(1.0 / (1.0 + np.std(edge_strength) / (np.mean(edge_strength) + 1e-9)))

        patch_entropy = self._patch_entropy(image)
        spectral_flatness = float(np.exp(np.mean(np.log(magnitude + 1e-9))) / (np.mean(magnitude) + 1e-9))

        return {
            "fft_magnitude_mean": float(np.mean(magnitude)),
            "high_frequency_energy": high_energy,
            "low_frequency_ratio": low_ratio,
            "noise_residual": noise_residual,
            "edge_consistency": edge_consistency,
            "patch_entropy": patch_entropy,
            "spectral_flatness": spectral_flatness,
        }

    def _signals(self, features: dict[str, float]) -> list[dict[str, Any]]:
        return [
            {
                "type": "spectral_anomaly",
                "label": "spectral anomaly",
                "value": features["spectral_flatness"],
                "weight": 0.22,
                "matched": features["spectral_flatness"] > 0.74,
            },
            {
                "type": "high_frequency_energy",
                "label": "high-frequency energy elevated",
                "value": features["high_frequency_energy"],
                "weight": 0.18,
                "matched": features["high_frequency_energy"] > 1.08,
            },
            {
                "type": "low_frequency_ratio",
                "label": "low-frequency ratio unusually smooth",
                "value": features["low_frequency_ratio"],
                "weight": 0.14,
                "matched": features["low_frequency_ratio"] < 0.92,
            },
            {
                "type": "noise_residual",
                "label": "diffusion-like noise residual",
                "value": features["noise_residual"],
                "weight": 0.2,
                "matched": 0.015 <= features["noise_residual"] <= 0.09,
            },
            {
                "type": "edge_consistency",
                "label": "edge consistency is unusually regular",
                "value": features["edge_consistency"],
                "weight": 0.14,
                "matched": features["edge_consistency"] > 0.55,
            },
            {
                "type": "patch_entropy",
                "label": "patch entropy suggests synthetic texture",
                "value": features["patch_entropy"],
                "weight": 0.12,
                "matched": 3.0 <= features["patch_entropy"] <= 6.8,
            },
        ]

    def _camera_penalty(self, features: dict[str, float]) -> float:
        if features["noise_residual"] > 0.16 and features["patch_entropy"] > 6.5:
            return -0.18
        if features["spectral_flatness"] > 0.8:
            return 0.08
        return 0.0

    def _resize_for_analysis(self, image: np.ndarray) -> np.ndarray:
        height, width = image.shape
        max_side = max(height, width)
        if max_side <= 256:
            return image.astype(np.float64)
        step = max(1, max_side // 256)
        return image[::step, ::step].astype(np.float64)

    def _box_blur(self, image: np.ndarray) -> np.ndarray:
        padded = np.pad(image, 1, mode="edge")
        return (
            padded[:-2, :-2]
            + padded[:-2, 1:-1]
            + padded[:-2, 2:]
            + padded[1:-1, :-2]
            + padded[1:-1, 1:-1]
            + padded[1:-1, 2:]
            + padded[2:, :-2]
            + padded[2:, 1:-1]
            + padded[2:, 2:]
        ) / 9.0

    def _patch_entropy(self, image: np.ndarray) -> float:
        patch_size = 16
        entropies: list[float] = []
        for y in range(0, image.shape[0] - patch_size + 1, patch_size):
            for x in range(0, image.shape[1] - patch_size + 1, patch_size):
                patch = image[y : y + patch_size, x : x + patch_size]
                histogram, _ = np.histogram(patch, bins=32, range=(0, 255), density=True)
                probabilities = histogram / (histogram.sum() + 1e-9)
                entropies.append(float(-np.sum(probabilities * np.log2(probabilities + 1e-9))))
        return float(np.mean(entropies)) if entropies else 0.0

    def _decode_image(self, content_base64: str, mime_type: str) -> np.ndarray | None:
        try:
            file_bytes = base64.b64decode(content_base64)
        except ValueError:
            return None
        if mime_type == "image/png" or file_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
            return self._decode_png(file_bytes)
        if file_bytes.startswith(b"P5") or file_bytes.startswith(b"P2"):
            return self._decode_pgm(file_bytes)
        return None

    def _decode_png(self, file_bytes: bytes) -> np.ndarray | None:
        if not file_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
            return None
        offset = 8
        width = height = color_type = bit_depth = None
        compressed = bytearray()
        while offset + 12 <= len(file_bytes):
            length = int.from_bytes(file_bytes[offset : offset + 4], "big")
            chunk_type = file_bytes[offset + 4 : offset + 8]
            data_start = offset + 8
            data_end = data_start + length
            if data_end + 4 > len(file_bytes):
                return None
            data = file_bytes[data_start:data_end]
            if chunk_type == b"IHDR":
                width, height, bit_depth, color_type = struct.unpack(">IIBB", data[:10])
            elif chunk_type == b"IDAT":
                compressed.extend(data)
            elif chunk_type == b"IEND":
                break
            offset = data_end + 4
        if width is None or height is None or bit_depth != 8 or color_type not in {0, 2, 6}:
            return None
        channels = {0: 1, 2: 3, 6: 4}[color_type]
        try:
            raw = zlib.decompress(bytes(compressed))
        except zlib.error:
            return None
        stride = width * channels
        rows = []
        previous = np.zeros(stride, dtype=np.uint8)
        cursor = 0
        for _ in range(height):
            if cursor >= len(raw):
                return None
            filter_type = raw[cursor]
            cursor += 1
            row = np.frombuffer(raw[cursor : cursor + stride], dtype=np.uint8).copy()
            cursor += stride
            row = self._unfilter_png_row(row, previous, filter_type, channels)
            rows.append(row)
            previous = row
        pixels = np.vstack(rows).reshape((height, width, channels))
        if channels == 1:
            return pixels[:, :, 0].astype(np.float64)
        return pixels[:, :, :3].astype(np.float64).mean(axis=2)

    def _unfilter_png_row(
        self,
        row: np.ndarray,
        previous: np.ndarray,
        filter_type: int,
        bytes_per_pixel: int,
    ) -> np.ndarray:
        result = row.astype(np.int16)
        if filter_type == 0:
            return row
        for index in range(len(result)):
            left = result[index - bytes_per_pixel] if index >= bytes_per_pixel else 0
            up = int(previous[index])
            up_left = int(previous[index - bytes_per_pixel]) if index >= bytes_per_pixel else 0
            if filter_type == 1:
                result[index] = (result[index] + left) & 0xFF
            elif filter_type == 2:
                result[index] = (result[index] + up) & 0xFF
            elif filter_type == 3:
                result[index] = (result[index] + ((left + up) // 2)) & 0xFF
            elif filter_type == 4:
                result[index] = (result[index] + self._paeth(left, up, up_left)) & 0xFF
        return result.astype(np.uint8)

    def _paeth(self, left: int, up: int, up_left: int) -> int:
        estimate = left + up - up_left
        distances = [abs(estimate - left), abs(estimate - up), abs(estimate - up_left)]
        if distances[0] <= distances[1] and distances[0] <= distances[2]:
            return left
        if distances[1] <= distances[2]:
            return up
        return up_left

    def _decode_pgm(self, file_bytes: bytes) -> np.ndarray | None:
        parts = file_bytes.split()
        if len(parts) < 4 or parts[0] not in {b"P5", b"P2"}:
            return None
        width = int(parts[1])
        height = int(parts[2])
        max_value = int(parts[3])
        if max_value <= 0:
            return None
        if parts[0] == b"P2":
            values = np.array([int(value) for value in parts[4:]], dtype=np.float64)
        else:
            header = b"\n".join(parts[:4]) + b"\n"
            start = file_bytes.find(header)
            if start < 0:
                return None
            values = np.frombuffer(file_bytes[start + len(header) :], dtype=np.uint8).astype(np.float64)
        if values.size < width * height:
            return None
        return values[: width * height].reshape((height, width)) * (255.0 / max_value)
