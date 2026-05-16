from __future__ import annotations

import base64
import re
import struct
from typing import Any

from app.schemas.smfp_metadata import SmfpMetadataExtractRequest


class SmfpMetadataService:
    def extract(self, payload: SmfpMetadataExtractRequest) -> dict[str, Any]:
        file_bytes = self._decode_content(payload.content_base64)
        mime_type = payload.mime_type or self._infer_mime(payload.filename)
        extracted: dict[str, Any] = {
            "exif": {},
            "xmp": {},
            "png_chunks": [],
            "pdf_metadata": {},
            "software": [],
            "creation_tool": "unknown",
            "dimensions": {},
        }
        signals: list[dict[str, Any]] = []
        limitations = [
            "Metadata is weak to medium evidence, not absolute proof of origin",
            "Metadata may be removed or falsified",
            "Absence of metadata is not proof of origin",
            "No official C2PA provenance detected",
        ]

        if payload.metadata:
            extracted["provided_metadata"] = payload.metadata
            self._collect_software_from_mapping(payload.metadata, extracted, signals)

        if file_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
            self._extract_png(file_bytes, extracted, signals)
        elif file_bytes.startswith(b"%PDF"):
            self._extract_pdf(file_bytes, extracted, signals)
        elif file_bytes.startswith(b"\xff\xd8"):
            self._extract_jpeg(file_bytes, extracted, signals)

        xmp = self._extract_xmp(file_bytes)
        if xmp:
            extracted["xmp"] = {"raw": xmp}
            self._collect_software_from_text(xmp, extracted, signals, "xmp_signal")

        if not self._has_any_metadata(extracted):
            limitations.append("No embedded metadata detected in the provided sample")

        extracted["software"] = sorted(set(extracted["software"]))
        if extracted["software"] and extracted["creation_tool"] == "unknown":
            extracted["creation_tool"] = extracted["software"][0]

        return {
            "mime_type": mime_type,
            "extracted": extracted,
            "signals": signals,
            "limitations": limitations,
        }

    def _decode_content(self, content_base64: str | None) -> bytes:
        if not content_base64:
            return b""
        try:
            return base64.b64decode(content_base64)
        except ValueError:
            return b""

    def _extract_png(self, file_bytes: bytes, extracted: dict[str, Any], signals: list[dict[str, Any]]) -> None:
        if len(file_bytes) >= 24:
            width, height = struct.unpack(">II", file_bytes[16:24])
            extracted["dimensions"] = {"width": width, "height": height}
            if self._looks_like_generated_dimensions(width, height):
                signals.append(
                    {
                        "type": "dimension_signal",
                        "label": f"image dimensions look generation-friendly ({width}x{height})",
                        "producer_hint": "unknown",
                        "weight": 0.12,
                        "matched": True,
                    }
                )

        offset = 8
        while offset + 12 <= len(file_bytes):
            length = int.from_bytes(file_bytes[offset : offset + 4], "big")
            chunk_type = file_bytes[offset + 4 : offset + 8].decode("latin-1", errors="replace")
            data_start = offset + 8
            data_end = data_start + length
            if data_end + 4 > len(file_bytes):
                break
            data = file_bytes[data_start:data_end]
            chunk_record: dict[str, Any] = {"type": chunk_type, "length": length}
            if chunk_type in {"tEXt", "iTXt", "zTXt"}:
                text = self._decode_text(data)
                chunk_record["text"] = text
                self._collect_software_from_text(text, extracted, signals, "png_text_chunk")
            extracted["png_chunks"].append(chunk_record)
            offset = data_end + 4
            if chunk_type == "IEND":
                break

    def _extract_pdf(self, file_bytes: bytes, extracted: dict[str, Any], signals: list[dict[str, Any]]) -> None:
        text = file_bytes[:200000].decode("latin-1", errors="ignore")
        metadata: dict[str, str] = {}
        for key in ["Title", "Author", "Creator", "Producer", "CreationDate", "ModDate"]:
            match = re.search(rf"/{key}\s*\((.*?)\)", text, flags=re.DOTALL)
            if match:
                metadata[key] = self._clean_pdf_string(match.group(1))
        extracted["pdf_metadata"] = metadata
        self._collect_software_from_mapping(metadata, extracted, signals)

    def _extract_jpeg(self, file_bytes: bytes, extracted: dict[str, Any], signals: list[dict[str, Any]]) -> None:
        offset = 2
        while offset + 4 < len(file_bytes):
            if file_bytes[offset] != 0xFF:
                break
            marker = file_bytes[offset + 1]
            if marker in {0xDA, 0xD9}:
                break
            length = int.from_bytes(file_bytes[offset + 2 : offset + 4], "big")
            segment = file_bytes[offset + 4 : offset + 2 + length]
            if marker == 0xE1 and segment.startswith(b"Exif\x00\x00"):
                extracted["exif"] = {"present": True, "app1_length": length}
                signals.append(
                    {
                        "type": "exif_signal",
                        "label": "EXIF APP1 segment detected",
                        "producer_hint": "unknown",
                        "weight": 0.1,
                        "matched": True,
                    }
                )
            offset += 2 + length

    def _extract_xmp(self, file_bytes: bytes) -> str:
        if not file_bytes:
            return ""
        text = file_bytes[:300000].decode("utf-8", errors="ignore")
        match = re.search(r"(<x:xmpmeta[\s\S]*?</x:xmpmeta>)", text)
        return match.group(1) if match else ""

    def _collect_software_from_mapping(
        self,
        metadata: dict[str, Any],
        extracted: dict[str, Any],
        signals: list[dict[str, Any]],
    ) -> None:
        for key, value in metadata.items():
            label = f"{key}: {value}"
            self._collect_software_from_text(str(value), extracted, signals, "software_tag", label_prefix=label)

    def _collect_software_from_text(
        self,
        text: str,
        extracted: dict[str, Any],
        signals: list[dict[str, Any]],
        signal_type: str,
        *,
        label_prefix: str | None = None,
    ) -> None:
        lowered = text.lower()
        hints = [
            (["chatgpt", "dall-e", "openai"], "openai_like", "metadata mentions OpenAI/ChatGPT/DALL-E", 0.42),
            (["midjourney"], "midjourney_like", "metadata mentions Midjourney", 0.42),
            (["flux"], "flux_like", "metadata mentions Flux", 0.35),
            (["stable diffusion", "comfyui", "automatic1111"], "stable_diffusion_like", "metadata mentions Stable Diffusion tooling", 0.42),
            (["gemini"], "gemini_like", "metadata mentions Gemini", 0.35),
            (["sora"], "sora_like", "metadata mentions Sora", 0.35),
        ]
        for needles, producer_hint, label, weight in hints:
            if not any(needle in lowered for needle in needles):
                continue
            extracted["software"].append(producer_hint.replace("_like", ""))
            extracted["creation_tool"] = producer_hint
            signals.append(
                {
                    "type": signal_type,
                    "label": label_prefix or label,
                    "producer_hint": producer_hint,
                    "weight": weight,
                    "matched": True,
                }
            )

    def _decode_text(self, data: bytes) -> str:
        if b"\x00" in data:
            data = data.replace(b"\x00", b" ")
        return data.decode("utf-8", errors="ignore").strip()

    def _clean_pdf_string(self, value: str) -> str:
        return value.replace(r"\)", ")").replace(r"\(", "(").replace("\\\\", "\\").strip()

    def _looks_like_generated_dimensions(self, width: int, height: int) -> bool:
        common = {512, 768, 896, 1024, 1152, 1216, 1344, 1536, 1792, 2048}
        return width in common or height in common or abs(width - height) <= 8

    def _has_any_metadata(self, extracted: dict[str, Any]) -> bool:
        return bool(
            extracted.get("exif")
            or extracted.get("xmp")
            or extracted.get("pdf_metadata")
            or extracted.get("software")
            or any(chunk.get("type") in {"tEXt", "iTXt", "zTXt"} for chunk in extracted.get("png_chunks", []))
        )

    def _infer_mime(self, filename: str) -> str:
        extension = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
        return {
            "png": "image/png",
            "jpg": "image/jpeg",
            "jpeg": "image/jpeg",
            "pdf": "application/pdf",
        }.get(extension, "application/octet-stream")
