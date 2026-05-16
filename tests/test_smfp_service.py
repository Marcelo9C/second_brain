import base64
import json
import tempfile
import unittest
from pathlib import Path

from nacl.signing import SigningKey, VerifyKey

from app.schemas.smfp import SmfpAssetCreate, SmfpRevisionCreate
from app.services.smfp_service import SmfpService


class SmfpServiceTest(unittest.TestCase):
    def test_ingest_asset_creates_manifest_signature_and_trust(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = SmfpService(
                storage_dir=Path(tmp),
                signing_secret="unit-secret",
                public_key_id="unit-key",
            )

            result = service.ingest_asset(
                SmfpAssetCreate(
                    filename="note.txt",
                    mime_type="text/plain",
                    content_text="Synthetic evidence sample.",
                    model="gemini-2.5",
                    prompt="Create a sample.",
                )
            )

            manifest = result["manifest"]
            self.assertTrue(result["asset_id"].startswith("smfp_"))
            self.assertEqual(manifest["key_id"], "unit-key")
            self.assertEqual(manifest["public_key_id"], "unit-key")
            self.assertEqual(manifest["signature_algorithm"], "Ed25519")
            self.assertEqual(manifest["signature_mode"], "PUBLIC_ED25519")
            self.assertTrue(manifest["public_key"])
            self.assertIn("signed_payload", manifest)
            self.assertEqual(len(manifest["revisions"]), 1)
            self.assertEqual(manifest["revisions"][0]["signature_algorithm"], "Ed25519")
            self.assertEqual(result["audit_report"]["trust"]["trust_score"], 100)

            public_key = service.get_public_key("unit-key")
            self.assertEqual(public_key["signature_algorithm"], "Ed25519")
            self.assertEqual(public_key["public_key"], manifest["public_key"])
            self.assertEqual(public_key["status"], "active")
            self.assertEqual(service.list_public_keys()["keys"][0]["key_id"], "unit-key")

    def test_public_ed25519_uses_configured_private_seed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            seed = bytes.fromhex("11" * 32)
            service = SmfpService(
                storage_dir=Path(tmp),
                signing_secret="unit-secret",
                key_id="dashem-prod-2026-01",
                private_key=seed.hex(),
            )

            result = service.ingest_asset(SmfpAssetCreate(content_text="Public provenance."))
            manifest = result["manifest"]
            expected_public_key = SigningKey(seed).verify_key.encode()

            self.assertEqual(manifest["key_id"], "dashem-prod-2026-01")
            self.assertEqual(manifest["signature_mode"], "PUBLIC_ED25519")
            self.assertEqual(manifest["signature_algorithm"], "Ed25519")
            self.assertEqual(
                service.get_public_key("dashem-prod-2026-01")["public_key"],
                manifest["public_key"],
            )
            VerifyKey(expected_public_key).verify(
                service._canonical_bytes(manifest["signed_payload"]),
                base64.b64decode(manifest["signature"]),
            )

    def test_revision_chain_verifies(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = SmfpService(
                storage_dir=Path(tmp),
                signing_secret="unit-secret",
            )
            created = service.ingest_asset(
                SmfpAssetCreate(
                    filename="claim.txt",
                    mime_type="text/plain",
                    content_text="First version.",
                )
            )

            service.add_revision(
                created["asset_id"],
                SmfpRevisionCreate(
                    content_text="Second version.",
                    editor="reviewer",
                    operation="normalize",
                ),
            )
            verification = service.verify_asset(created["asset_id"])

            self.assertTrue(verification["content_hash_valid"])
            self.assertTrue(verification["signature_valid"])
            self.assertTrue(verification["chain_valid"])
            self.assertEqual(verification["audit_report"]["trust"]["provenance"], "verified")
            self.assertEqual(verification["signature_algorithm"], "Ed25519")
            self.assertEqual(verification["signature_mode"], "PUBLIC_ED25519")

    def test_rotation_accepts_retired_key_and_signs_new_revision_with_active_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            storage_dir = Path(tmp)
            old_seed = bytes.fromhex("22" * 32)
            new_seed = bytes.fromhex("33" * 32)
            old_service = SmfpService(
                storage_dir=storage_dir,
                signing_secret="unit-secret",
                key_id="old-key",
                private_key=old_seed.hex(),
            )
            created = old_service.ingest_asset(SmfpAssetCreate(content_text="Original signed asset."))

            self._replace_registry(
                storage_dir,
                [
                    self._registry_key("old-key", old_seed, "retired"),
                    self._registry_key("new-key", new_seed, "active"),
                ],
            )
            new_service = SmfpService(
                storage_dir=storage_dir,
                signing_secret="unit-secret",
                key_id="new-key",
                private_key=new_seed.hex(),
            )

            verification = new_service.verify_asset(created["asset_id"])
            self.assertTrue(verification["signature_valid"])
            self.assertTrue(verification["chain_valid"])

            updated = new_service.add_revision(
                created["asset_id"],
                SmfpRevisionCreate(content_text="Revision signed after rotation."),
            )
            manifest = updated["manifest"]
            self.assertEqual(manifest["key_id"], "new-key")
            self.assertEqual(manifest["revisions"][0]["key_id"], "old-key")
            self.assertEqual(manifest["revisions"][1]["key_id"], "new-key")

            verification = new_service.verify_asset(created["asset_id"])
            self.assertTrue(verification["signature_valid"])
            self.assertTrue(verification["chain_valid"])

    def test_revoked_key_rejects_manifest_and_revision_verification(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            storage_dir = Path(tmp)
            old_seed = bytes.fromhex("44" * 32)
            new_seed = bytes.fromhex("55" * 32)
            old_service = SmfpService(
                storage_dir=storage_dir,
                signing_secret="unit-secret",
                key_id="old-key",
                private_key=old_seed.hex(),
            )
            created = old_service.ingest_asset(SmfpAssetCreate(content_text="Revoked provenance."))

            self._replace_registry(
                storage_dir,
                [
                    self._registry_key("old-key", old_seed, "revoked"),
                    self._registry_key("new-key", new_seed, "active"),
                ],
            )
            new_service = SmfpService(
                storage_dir=storage_dir,
                signing_secret="unit-secret",
                key_id="new-key",
                private_key=new_seed.hex(),
            )

            verification = new_service.verify_asset(created["asset_id"])
            self.assertFalse(verification["signature_valid"])
            self.assertFalse(verification["chain_valid"])
            self.assertEqual(verification["audit_report"]["trust"]["signature"], "invalid")

    def test_public_manifest_verify_rejects_revoked_key_independent_of_origin_analysis(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            storage_dir = Path(tmp)
            old_seed = bytes.fromhex("66" * 32)
            new_seed = bytes.fromhex("77" * 32)
            old_service = SmfpService(
                storage_dir=storage_dir,
                signing_secret="unit-secret",
                key_id="old-key",
                private_key=old_seed.hex(),
            )
            created = old_service.ingest_asset(SmfpAssetCreate(content_text="Public verify revoked."))

            self._replace_registry(
                storage_dir,
                [
                    self._registry_key("old-key", old_seed, "revoked"),
                    self._registry_key("new-key", new_seed, "active"),
                ],
            )
            new_service = SmfpService(
                storage_dir=storage_dir,
                signing_secret="unit-secret",
                key_id="new-key",
                private_key=new_seed.hex(),
            )

            verification = new_service.verify_manifest_content(
                manifest=created["manifest"],
                content=b"Public verify revoked.",
            )

            self.assertEqual(verification["key_status"], "revoked")
            self.assertFalse(verification["signature_valid"])
            self.assertEqual(verification["audit_report"]["trust"]["signature"], "invalid")

    def test_chain_tampering_reduces_trust(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = SmfpService(
                storage_dir=Path(tmp),
                signing_secret="unit-secret",
            )
            created = service.ingest_asset(
                SmfpAssetCreate(content_text="Original.")
            )
            manifest = service.get_manifest(created["asset_id"])
            manifest["revisions"][0]["parent_hash"] = "tampered"
            service._write_manifest(manifest)

            verification = service.verify_asset(created["asset_id"])

            self.assertFalse(verification["chain_valid"])
            self.assertEqual(verification["audit_report"]["trust"]["tampering"], "suspected")
            self.assertLess(verification["audit_report"]["trust"]["trust_score"], 100)

    def test_legacy_hmac_mode_is_capped_and_diagnostic(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = SmfpService(
                storage_dir=Path(tmp),
                signing_secret="unit-secret",
                key_id="lab-key",
                signature_mode="LAB_HMAC",
            )

            result = service.ingest_asset(SmfpAssetCreate(content_text="Legacy mode."))

            manifest = result["manifest"]
            self.assertEqual(manifest["signature_algorithm"], "HMAC-SHA256")
            self.assertEqual(manifest["signature_mode"], "LAB_HMAC")
            self.assertLessEqual(result["audit_report"]["trust"]["trust_score"], 74)

    def _registry_key(self, key_id: str, seed: bytes, status: str) -> dict[str, str]:
        return {
            "key_id": key_id,
            "public_key": base64.b64encode(SigningKey(seed).verify_key.encode()).decode("ascii"),
            "status": status,
            "created_at": "2026-05-15T00:00:00+00:00",
        }

    def _replace_registry(self, storage_dir: Path, keys: list[dict[str, str]]) -> None:
        (storage_dir / "key_registry.json").write_text(
            json.dumps({"keys": keys}, indent=2, sort_keys=True),
            encoding="utf-8",
        )
