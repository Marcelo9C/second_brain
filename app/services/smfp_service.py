from __future__ import annotations

import base64
import hashlib
import hmac
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from nacl.exceptions import BadSignatureError
from nacl.signing import SigningKey, VerifyKey

from app.schemas.smfp import SmfpAssetCreate, SmfpRevisionCreate
from app.services.smfp_json import canonical_json_bytes


class SmfpService:
    def __init__(
        self,
        *,
        storage_dir: Path,
        signing_secret: str,
        key_id: str = "dashem-ed25519-dev-01",
        public_key_id: str | None = None,
        signature_mode: str = "PUBLIC_ED25519",
        private_key: str | None = None,
        private_key_file: Path | None = None,
    ) -> None:
        self.storage_dir = storage_dir
        self.asset_dir = storage_dir / "assets"
        self.manifest_dir = storage_dir / "manifests"
        self.key_registry_path = storage_dir / "key_registry.json"
        self.signing_secret = signing_secret.encode("utf-8")
        self.key_id = public_key_id or key_id
        self.signature_mode = signature_mode.upper()
        self.private_key_seed = self._load_private_key_seed(
            private_key=private_key,
            private_key_file=private_key_file,
            fallback_secret=signing_secret,
        )
        self.public_key = self._public_key_from_seed(self.private_key_seed)
        self.asset_dir.mkdir(parents=True, exist_ok=True)
        self.manifest_dir.mkdir(parents=True, exist_ok=True)
        self._ensure_active_key_registered()

    def ingest_asset(self, payload: SmfpAssetCreate) -> dict[str, Any]:
        content = self._content_bytes(payload.content_base64, payload.content_text)
        content_hash = self._sha256(content)
        asset_id = f"smfp_{content_hash[:16]}"
        created_at = self._now()
        prompt_hash = self._sha256(payload.prompt.encode("utf-8")) if payload.prompt else None

        signed_payload = self._manifest_signed_payload(
            {
                "asset_id": asset_id,
                "content_hash": content_hash,
                "created_at": created_at,
                "key_id": self.signing_key_id,
            }
        )
        signature = self._sign(signed_payload)
        initial_revision = self._revision_record(
            revision=0,
            parent_hash=None,
            content=content,
            editor=payload.created_by,
            operation="ingest",
            metadata={"source": payload.source},
        )
        manifest = {
            "asset_id": asset_id,
            "created_by": payload.created_by,
            "model": payload.model,
            "prompt_hash": prompt_hash,
            "content_hash": content_hash,
            "signature": signature,
            "signature_algorithm": self.signature_algorithm,
            "signature_mode": self.signature_mode,
            "key_id": self.signing_key_id,
            "public_key_id": self.signing_key_id,
            "public_key": self.signing_public_key,
            "signed_payload": signed_payload,
            "created_at": created_at,
            "filename": payload.filename,
            "mime_type": payload.mime_type,
            "source": payload.source,
            "size_bytes": len(content),
            "metadata": payload.metadata,
            "revisions": [initial_revision],
        }
        self._asset_path(asset_id).write_bytes(content)
        self._write_manifest(manifest)
        return {
            "asset_id": asset_id,
            "content_hash": content_hash,
            "manifest": manifest,
            "audit_report": self.audit_report(manifest),
        }

    def add_revision(self, asset_id: str, payload: SmfpRevisionCreate) -> dict[str, Any]:
        manifest = self.get_manifest(asset_id)
        content = self._content_bytes(payload.content_base64, payload.content_text)
        previous = manifest["revisions"][-1]
        revision = self._revision_record(
            revision=len(manifest["revisions"]),
            parent_hash=previous["revision_hash"],
            content=content,
            editor=payload.editor,
            operation=payload.operation,
            metadata=payload.metadata,
        )
        manifest["revisions"].append(revision)
        manifest["content_hash"] = self._sha256(content)
        manifest["size_bytes"] = len(content)
        manifest["updated_at"] = self._now()
        manifest["signed_payload"] = self._manifest_signed_payload(
            {
                "asset_id": manifest["asset_id"],
                "content_hash": manifest["content_hash"],
                "created_at": manifest["created_at"],
                "key_id": self.signing_key_id,
                "updated_at": manifest["updated_at"],
            }
        )
        manifest["signature"] = self._sign(manifest["signed_payload"])
        manifest["signature_algorithm"] = self.signature_algorithm
        manifest["signature_mode"] = self.signature_mode
        manifest["key_id"] = self.signing_key_id
        manifest["public_key_id"] = self.signing_key_id
        manifest["public_key"] = self.signing_public_key
        self._asset_path(asset_id).write_bytes(content)
        self._write_manifest(manifest)
        return {
            "asset_id": asset_id,
            "revision": revision,
            "manifest": manifest,
            "audit_report": self.audit_report(manifest),
        }

    def get_manifest(self, asset_id: str) -> dict[str, Any]:
        path = self._manifest_path(asset_id)
        if not path.exists():
            raise FileNotFoundError(f"SMFP asset not found: {asset_id}")
        return json.loads(path.read_text(encoding="utf-8"))

    def verify_asset(self, asset_id: str) -> dict[str, Any]:
        manifest = self.get_manifest(asset_id)
        asset_bytes = self._asset_path(asset_id).read_bytes()
        return self.verify_manifest_content(manifest=manifest, content=asset_bytes)

    def verify_manifest_content(self, *, manifest: dict[str, Any], content: bytes) -> dict[str, Any]:
        content_hash_valid = self._sha256(content) == manifest.get("content_hash")
        signature_valid = self._verify_signature(manifest)
        chain_valid = self._chain_valid(manifest.get("revisions", []))
        key_id = manifest.get("key_id") or manifest.get("public_key_id")
        key_status = self._key_status(str(key_id)) if key_id else "unknown"
        report = self.audit_report(
            manifest,
            content_hash_valid=content_hash_valid,
            signature_valid=signature_valid,
            chain_valid=chain_valid,
        )
        return {
            "asset_id": manifest.get("asset_id"),
            "content_hash_valid": content_hash_valid,
            "signature_valid": signature_valid,
            "signature_mode": manifest.get("signature_mode"),
            "signature_algorithm": manifest.get("signature_algorithm"),
            "key_id": key_id,
            "key_status": key_status,
            "chain_valid": chain_valid,
            "tampering": "none" if content_hash_valid and chain_valid else "suspected",
            "audit_report": report,
        }

    def get_public_key(self, key_id: str) -> dict[str, Any]:
        key = self._registry_by_id().get(key_id)
        if not key:
            raise KeyError(f"SMFP public key not found: {key_id}")
        return {
            "key_id": key["key_id"],
            "public_key": key["public_key"],
            "status": key["status"],
            "created_at": key["created_at"],
            "signature_algorithm": "Ed25519",
            "signature_mode": "PUBLIC_ED25519",
            "encoding": "base64-raw",
        }

    def list_public_keys(self) -> dict[str, Any]:
        keys = [
            {
                "key_id": key["key_id"],
                "public_key": key["public_key"],
                "status": key["status"],
                "created_at": key["created_at"],
                "signature_algorithm": "Ed25519",
                "signature_mode": "PUBLIC_ED25519",
                "encoding": "base64-raw",
            }
            for key in self._load_key_registry()
        ]
        return {"keys": keys}

    def audit_report(
        self,
        manifest: dict[str, Any],
        *,
        content_hash_valid: bool = True,
        signature_valid: bool | None = None,
        chain_valid: bool | None = None,
    ) -> dict[str, Any]:
        signature_valid = self._verify_signature(manifest) if signature_valid is None else signature_valid
        chain_valid = self._chain_valid(manifest.get("revisions", [])) if chain_valid is None else chain_valid
        metadata_removed = not bool(manifest.get("metadata"))
        trust_score = self._trust_score(
            manifest,
            content_hash_valid=content_hash_valid,
            signature_valid=signature_valid,
            chain_valid=chain_valid,
        )
        possible_model = self._possible_model(manifest)
        return {
            "asset_id": manifest["asset_id"],
            "chain_valid": chain_valid,
            "watermark_detected": False,
            "metadata_removed": metadata_removed,
            "possible_model": possible_model,
            "confidence": 0.72 if signature_valid and chain_valid else 0.38,
            "trust": {
                "trust_score": trust_score,
                "provenance": "verified" if trust_score >= 85 else "partial" if trust_score >= 50 else "unverified",
                "signature": "valid" if signature_valid else "invalid",
                "signature_mode": manifest.get("signature_mode", "LAB_HMAC"),
                "signature_algorithm": manifest.get("signature_algorithm", "HMAC-SHA256"),
                "key_id": manifest.get("key_id") or manifest.get("public_key_id"),
                "tampering": "none" if content_hash_valid and chain_valid else "suspected",
                "ai_probability": 0.68 if manifest.get("model") or manifest.get("prompt_hash") else 0.18,
            },
        }

    def _trust_score(
        self,
        manifest: dict[str, Any],
        *,
        content_hash_valid: bool,
        signature_valid: bool,
        chain_valid: bool,
    ) -> int:
        score = 0
        score += 30 if content_hash_valid and manifest.get("content_hash") else 0
        score += 25 if signature_valid else 0
        score += 25 if chain_valid else 0
        score += 10 if manifest.get("asset_id") and manifest.get("created_at") else 0
        score += 10 if manifest.get("mime_type") and manifest.get("size_bytes") is not None else 0
        if manifest.get("signature_mode") == "LAB_HMAC":
            score = min(score, 74)
        return min(score, 100)

    def _revision_record(
        self,
        *,
        revision: int,
        parent_hash: str | None,
        content: bytes,
        editor: str,
        operation: str,
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        timestamp = self._now()
        delta_hash = self._sha256(content)
        base = {
            "revision": revision,
            "parent_hash": parent_hash,
            "delta_hash": delta_hash,
            "editor": editor,
            "operation": operation,
            "timestamp": timestamp,
            "metadata": metadata,
        }
        signed_payload = self._revision_signed_payload(base)
        return {
            **base,
            "revision_hash": self._sha256(self._canonical_json(base).encode("utf-8")),
            "signature": self._sign(signed_payload),
            "signature_algorithm": self.signature_algorithm,
            "signature_mode": self.signature_mode,
            "key_id": self.signing_key_id,
            "public_key": self.signing_public_key,
            "signed_payload": signed_payload,
        }

    def _chain_valid(self, revisions: list[dict[str, Any]]) -> bool:
        if not revisions:
            return False
        for index, revision in enumerate(revisions):
            parent_hash = revision.get("parent_hash")
            if index == 0 and parent_hash is not None:
                return False
            if index > 0 and parent_hash != revisions[index - 1].get("revision_hash"):
                return False
            if not self._verify_revision_signature(revision):
                return False
        return True

    def _verify_signature(self, manifest: dict[str, Any]) -> bool:
        signed_payload = manifest.get("signed_payload")
        if not isinstance(signed_payload, dict):
            signed_payload = self._manifest_signed_payload(
                {
                    "asset_id": manifest.get("asset_id"),
                    "content_hash": manifest.get("content_hash"),
                    "created_at": manifest.get("created_at"),
                    "key_id": manifest.get("key_id") or manifest.get("public_key_id"),
                    "updated_at": manifest.get("updated_at"),
                }
            )
        return self._verify_payload(
            signed_payload,
            str(manifest.get("signature", "")),
            str(manifest.get("public_key", "")),
            str(manifest.get("signature_mode", "LAB_HMAC")),
            key_id=manifest.get("key_id") or manifest.get("public_key_id"),
        )

    def _verify_revision_signature(self, revision: dict[str, Any]) -> bool:
        signed_payload = revision.get("signed_payload")
        if not isinstance(signed_payload, dict):
            signed_payload = self._revision_signed_payload(revision)
        return self._verify_payload(
            signed_payload,
            str(revision.get("signature", "")),
            str(revision.get("public_key", "")),
            str(revision.get("signature_mode", "LAB_HMAC")),
            key_id=revision.get("key_id"),
        )

    def _sign(self, payload: dict[str, Any]) -> str:
        canonical = self._canonical_bytes(payload)
        if self.signature_mode == "PUBLIC_ED25519":
            signature = SigningKey(self.private_key_seed).sign(canonical).signature
            return base64.b64encode(signature).decode("ascii")
        return hmac.new(
            self.signing_secret,
            canonical,
            hashlib.sha256,
        ).hexdigest()

    def _verify_payload(
        self,
        payload: dict[str, Any],
        signature: str,
        public_key: str,
        signature_mode: str,
        key_id: object | None = None,
    ) -> bool:
        canonical = self._canonical_bytes(payload)
        if signature_mode == "PUBLIC_ED25519":
            registry_key = self._registry_by_id().get(str(key_id)) if key_id else None
            if registry_key:
                if registry_key.get("status") == "revoked":
                    return False
                public_key = str(registry_key.get("public_key", ""))
            elif key_id:
                return False
            try:
                VerifyKey(base64.b64decode(public_key)).verify(
                    canonical,
                    base64.b64decode(signature),
                )
                return True
            except (BadSignatureError, ValueError, TypeError):
                return False
        expected = hmac.new(
            self.signing_secret,
            canonical,
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(expected, signature)

    @property
    def signature_algorithm(self) -> str:
        return "Ed25519" if self.signature_mode == "PUBLIC_ED25519" else "HMAC-SHA256"

    def _possible_model(self, manifest: dict[str, Any]) -> str:
        if manifest.get("model"):
            return str(manifest["model"])
        mime_type = str(manifest.get("mime_type", ""))
        if mime_type.startswith("image/"):
            return "image-or-diffusion-like"
        if mime_type.startswith("audio/"):
            return "audio-or-voice-like"
        if mime_type.startswith("video/"):
            return "video-or-synthetic-media-like"
        if mime_type.startswith("text/"):
            return "text-or-llm-like"
        return "unknown"

    def _content_bytes(self, content_base64: str | None, content_text: str | None) -> bytes:
        if content_base64:
            return base64.b64decode(content_base64)
        return (content_text or "").encode("utf-8")

    def _write_manifest(self, manifest: dict[str, Any]) -> None:
        self._manifest_path(manifest["asset_id"]).write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    def _manifest_path(self, asset_id: str) -> Path:
        return self.manifest_dir / f"{asset_id}.manifest.json"

    def _asset_path(self, asset_id: str) -> Path:
        return self.asset_dir / f"{asset_id}.bin"

    def _canonical_json(self, payload: dict[str, Any]) -> str:
        return self._canonical_bytes(payload).decode("utf-8")

    def _canonical_bytes(self, payload: dict[str, Any]) -> bytes:
        return canonical_json_bytes(payload)

    def _manifest_signed_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {key: value for key, value in payload.items() if value is not None}

    def _revision_signed_payload(self, revision: dict[str, Any]) -> dict[str, Any]:
        keys = [
            "revision",
            "parent_hash",
            "delta_hash",
            "editor",
            "operation",
            "timestamp",
            "metadata",
        ]
        return {key: revision.get(key) for key in keys if revision.get(key) is not None}

    def _sha256(self, content: bytes) -> str:
        return hashlib.sha256(content).hexdigest()

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    @property
    def signing_key_id(self) -> str:
        return self.active_key_id if self.signature_mode == "PUBLIC_ED25519" else self.key_id

    @property
    def signing_public_key(self) -> str:
        return self.active_public_key if self.signature_mode == "PUBLIC_ED25519" else ""

    @property
    def active_key_id(self) -> str:
        return self._active_key()["key_id"]

    @property
    def active_public_key(self) -> str:
        return self._active_key()["public_key"]

    def _active_key(self) -> dict[str, str]:
        registry = self._load_key_registry()
        for key in registry:
            if key.get("status") == "active":
                return key
        raise RuntimeError("SMFP key registry has no active key.")

    def _ensure_active_key_registered(self) -> None:
        if self.signature_mode != "PUBLIC_ED25519":
            return
        registry = self._load_key_registry()
        matching_key = next((key for key in registry if key.get("key_id") == self.key_id), None)
        if matching_key and matching_key.get("public_key") != self.public_key:
            raise ValueError(f"SMFP key registry public key mismatch for key_id: {self.key_id}")
        active_keys = [key for key in registry if key.get("status") == "active"]
        if len(active_keys) > 1:
            raise ValueError("SMFP key registry must have at most one active key.")
        if active_keys:
            active_key = active_keys[0]
            if active_key.get("key_id") != self.key_id or active_key.get("public_key") != self.public_key:
                raise ValueError("SMFP active key must match the configured key_id and private key.")
            return
        if not any(key.get("status") == "active" for key in registry):
            if matching_key:
                raise ValueError(f"SMFP configured key is {matching_key['status']}; configure an active key.")
            registry.append(
                {
                    "key_id": self.key_id,
                    "public_key": self.public_key,
                    "status": "active",
                    "created_at": self._now(),
                }
            )
            self._write_key_registry(registry)

    def _load_key_registry(self) -> list[dict[str, str]]:
        if not self.key_registry_path.exists():
            return []
        data = json.loads(self.key_registry_path.read_text(encoding="utf-8"))
        raw_keys = data.get("keys", data) if isinstance(data, dict) else data
        if not isinstance(raw_keys, list):
            raise ValueError("SMFP key registry must be a list or an object with a keys list.")
        registry: list[dict[str, str]] = []
        for item in raw_keys:
            if not isinstance(item, dict):
                raise ValueError("SMFP key registry entries must be objects.")
            key = {
                "key_id": str(item.get("key_id", "")),
                "public_key": str(item.get("public_key", "")),
                "status": str(item.get("status", "")),
                "created_at": str(item.get("created_at", "")),
            }
            if not key["key_id"] or not key["public_key"] or not key["created_at"]:
                raise ValueError("SMFP key registry entries require key_id, public_key, status, and created_at.")
            if key["status"] not in {"active", "retired", "revoked"}:
                raise ValueError(f"SMFP key registry has invalid status for key_id: {key['key_id']}")
            registry.append(key)
        return registry

    def _write_key_registry(self, registry: list[dict[str, str]]) -> None:
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.key_registry_path.write_text(
            json.dumps({"keys": registry}, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    def _registry_by_id(self) -> dict[str, dict[str, str]]:
        return {key["key_id"]: key for key in self._load_key_registry()}

    def _key_status(self, key_id: str) -> str:
        key = self._registry_by_id().get(key_id)
        return key["status"] if key else "unknown"

    def _load_private_key_seed(
        self,
        *,
        private_key: str | None,
        private_key_file: Path | None,
        fallback_secret: str,
    ) -> bytes:
        raw = private_key
        if not raw and private_key_file and private_key_file.exists():
            raw = private_key_file.read_text(encoding="utf-8").strip()
        if raw:
            return self._decode_private_key_seed(raw)
        return hashlib.sha256(f"smfp-ed25519-dev:{fallback_secret}".encode("utf-8")).digest()

    def _decode_private_key_seed(self, raw: str) -> bytes:
        value = raw.strip()
        if value.startswith("ed25519:"):
            value = value.split(":", 1)[1]
        try:
            seed = bytes.fromhex(value)
        except ValueError:
            seed = base64.b64decode(value)
        if len(seed) == 64:
            seed = seed[:32]
        if len(seed) != 32:
            raise ValueError("SMFP Ed25519 private key must be a 32-byte seed or 64-byte expanded key.")
        return seed

    def _public_key_from_seed(self, seed: bytes) -> str:
        return base64.b64encode(SigningKey(seed).verify_key.encode()).decode("ascii")
