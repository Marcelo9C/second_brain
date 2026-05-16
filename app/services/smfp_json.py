from __future__ import annotations

import json
from typing import Any

try:
    import orjson
except ImportError:  # pragma: no cover - exercised through health checks in minimal envs
    orjson = None


def canonical_json_bytes(payload: dict[str, Any]) -> bytes:
    if orjson is not None:
        return orjson.dumps(payload, option=orjson.OPT_SORT_KEYS)
    return json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
