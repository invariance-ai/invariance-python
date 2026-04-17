"""Deterministic canonical JSON + Ed25519 + SHA-256 primitives.

The canonical JSON output MUST be byte-identical to the TypeScript SDK's
`stableStringify` and the backend's `stableStringify` — any drift breaks
signatures cross-language.
"""

from __future__ import annotations

import hashlib
import json
import secrets
from typing import Any

from nacl.signing import SigningKey, VerifyKey
from nacl.exceptions import BadSignatureError


# ── Canonical JSON ─────────────────────────────────────────────────────────


def stable_stringify(value: Any) -> str:
    """Lexicographically sorted keys; arrays preserve order; no whitespace."""
    return json.dumps(
        _sort_keys(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _sort_keys(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _sort_keys(v) for k, v in sorted(value.items())}
    if isinstance(value, list):
        return [_sort_keys(v) for v in value]
    return value


# ── SHA-256 ────────────────────────────────────────────────────────────────


def sha256_hex(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def hash_node_payload(payload: dict[str, Any]) -> str:
    """Hash a NodeHashPayload dict.

    Expected keys: id, run_id, agent_id, parent_id, action_type,
    input, output, error, metadata, custom_fields, timestamp,
    duration_ms, previous_hashes.
    """
    return sha256_hex(stable_stringify(payload))


# ── Ed25519 ────────────────────────────────────────────────────────────────


def generate_keypair() -> tuple[str, str]:
    """Return (private_key_hex, public_key_hex) — 64-char hex each."""
    sk = SigningKey(secrets.token_bytes(32))
    return sk.encode().hex(), sk.verify_key.encode().hex()


def get_public_key(private_key_hex: str) -> str:
    return SigningKey(bytes.fromhex(private_key_hex)).verify_key.encode().hex()


def sign_ed25519(message_hex: str, private_key_hex: str) -> str:
    """Sign a hex message and return the 128-char hex signature."""
    sk = SigningKey(bytes.fromhex(private_key_hex))
    return sk.sign(bytes.fromhex(message_hex)).signature.hex()


def verify_ed25519(message_hex: str, signature_hex: str, public_key_hex: str) -> bool:
    try:
        vk = VerifyKey(bytes.fromhex(public_key_hex))
        vk.verify(bytes.fromhex(message_hex), bytes.fromhex(signature_hex))
        return True
    except (BadSignatureError, ValueError):
        return False
