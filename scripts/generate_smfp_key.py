from __future__ import annotations

import argparse
import base64
import json
from datetime import datetime, timezone
from pathlib import Path

from nacl.signing import SigningKey


ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_STORAGE_DIR = ROOT_DIR / "data" / "smfp"


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate an SMFP Ed25519 key once.")
    parser.add_argument("--key-id", required=True, help="Stable key id, for example dashem-prod-2026-05.")
    parser.add_argument("--storage-dir", type=Path, default=DEFAULT_STORAGE_DIR)
    parser.add_argument("--private-key-file", type=Path)
    parser.add_argument(
        "--retire-existing-active",
        action="store_true",
        help="Mark the current active key as retired before activating this key.",
    )
    args = parser.parse_args()

    storage_dir = args.storage_dir
    registry_path = storage_dir / "key_registry.json"
    private_key_file = args.private_key_file or storage_dir / "private_keys" / f"{args.key_id}.seed"

    if private_key_file.exists():
        raise SystemExit(f"Refusing to overwrite existing private key file: {private_key_file}")

    registry = load_registry(registry_path)
    if any(key["key_id"] == args.key_id for key in registry):
        raise SystemExit(f"Refusing to reuse existing SMFP key_id: {args.key_id}")

    active_keys = [key for key in registry if key["status"] == "active"]
    if active_keys and not args.retire_existing_active:
        raise SystemExit("An active SMFP key already exists. Use --retire-existing-active to rotate.")
    if len(active_keys) > 1:
        raise SystemExit("SMFP key registry has more than one active key.")
    if args.retire_existing_active:
        for key in active_keys:
            key["status"] = "retired"

    signing_key = SigningKey.generate()
    private_seed = base64.b64encode(signing_key.encode()).decode("ascii")
    public_key = base64.b64encode(signing_key.verify_key.encode()).decode("ascii")

    private_key_file.parent.mkdir(parents=True, exist_ok=True)
    private_key_file.write_text(private_seed, encoding="utf-8")
    try:
        private_key_file.chmod(0o600)
    except OSError:
        pass

    registry.append(
        {
            "key_id": args.key_id,
            "public_key": public_key,
            "status": "active",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    write_registry(registry_path, registry)

    print(f"SMFP key generated: {args.key_id}")
    print(f"Private key file: {private_key_file}")
    print(f"Key registry: {registry_path}")
    print("Set SMFP_KEY_ID and SMFP_PRIVATE_KEY_FILE to these values before signing.")


def load_registry(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    registry = data.get("keys", data) if isinstance(data, dict) else data
    if not isinstance(registry, list):
        raise SystemExit("SMFP key registry must be a list or an object with a keys list.")
    return [normalize_key(item) for item in registry]


def normalize_key(item: object) -> dict[str, str]:
    if not isinstance(item, dict):
        raise SystemExit("SMFP key registry entries must be objects.")
    key = {
        "key_id": str(item.get("key_id", "")),
        "public_key": str(item.get("public_key", "")),
        "status": str(item.get("status", "")),
        "created_at": str(item.get("created_at", "")),
    }
    if not key["key_id"] or not key["public_key"] or not key["created_at"]:
        raise SystemExit("SMFP key registry entries require key_id, public_key, status, and created_at.")
    if key["status"] not in {"active", "retired", "revoked"}:
        raise SystemExit(f"Invalid SMFP key status for {key['key_id']}: {key['status']}")
    return key


def write_registry(path: Path, registry: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"keys": registry}, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
