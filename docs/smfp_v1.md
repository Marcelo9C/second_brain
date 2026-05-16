# SMFP v1

Synthetic Media Forensics Pipeline starts as a provenance-first system.

## Flow

```text
input -> SHA-256 hash -> Ed25519 signature -> manifest -> signed revision chain -> public verification -> trust score
```

## MVP Scope

- SHA-256 content identity
- Ed25519 public-verification signatures
- HMAC-SHA256 only as legacy lab diagnostic mode
- C2PA-inspired manifest JSON
- Internal revision chain
- Verification endpoint
- Basic trust score

## Key Management

SMFP does not generate a new public-verification key on every boot. Generate the Ed25519 private seed once, persist it securely, and rotate it as an operational event by changing `SMFP_KEY_ID`.

```env
SMFP_SIGNATURE_MODE=PUBLIC_ED25519
SMFP_KEY_ID=dashem-prod-2026-01
SMFP_PRIVATE_KEY=
SMFP_PRIVATE_KEY_FILE=
```

`SMFP_PRIVATE_KEY` accepts a 32-byte Ed25519 seed as hex/base64. `SMFP_PRIVATE_KEY_FILE` can point to a secure local file containing the same value. HMAC-SHA256 remains available only as `LAB_HMAC` legacy/debug mode and is not the primary provenance signature.

## API

- `POST /api/smfp/assets`
- `GET /api/smfp/assets/{asset_id}/manifest`
- `GET /api/smfp/assets/{asset_id}/manifest/export`
- `POST /api/smfp/assets/{asset_id}/revisions`
- `GET /api/smfp/assets/{asset_id}/verify`
- `GET /api/smfp/public-keys/{key_id}`

## Next Upgrade

Add operational key rotation metadata and historical public-key lookup.
