"""Cryptographic handoff attestation tokens.

A HandoffToken is an Ed25519-signed, JWS-compact-like envelope that a sender
agent issues when calling ``run.handoff(to_agent_id=...)``. The receiving agent
passes ``.encode()`` back to the platform on ``runs.create(parent_handoff_token=...)``.

Token shape: ``base64url(header).base64url(claims).hex(signature)``

The signature is Ed25519 over ``sha256("<header_b64>.<claims_b64>")``.
"""

from __future__ import annotations

import base64
import json
import secrets
from dataclasses import dataclass, asdict
from typing import Any

from .crypto import sign_ed25519, sha256_hex


_HEADER = {"alg": "Ed25519", "typ": "INV-HO/1"}


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


@dataclass
class HandoffToken:
    """Signed delegation attestation. Opaque to the caller — use ``.encode()``."""

    iss_agent_id: str
    iss_run_id: str
    handoff_node_id: str
    handoff_node_hash: str
    to_agent_id: str
    iat: int
    exp: int
    nonce: str
    _signing_input: str
    _signature: str

    def encode(self) -> str:
        return f"{self._signing_input}.{self._signature}"


def build_handoff_token(
    *,
    iss_agent_id: str,
    iss_run_id: str,
    handoff_node_id: str,
    handoff_node_hash: str,
    to_agent_id: str,
    signing_key: str,
    iat_ms: int,
    ttl_ms: int = 10 * 60 * 1000,
    nonce: str | None = None,
) -> HandoffToken:
    exp = iat_ms + ttl_ms
    n = nonce or secrets.token_hex(16)
    claims: dict[str, Any] = {
        "iss_agent_id": iss_agent_id,
        "iss_run_id": iss_run_id,
        "handoff_node_id": handoff_node_id,
        "handoff_node_hash": handoff_node_hash,
        "to_agent_id": to_agent_id,
        "iat": iat_ms,
        "exp": exp,
        "nonce": n,
    }
    h_b64 = _b64url(json.dumps(_HEADER, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    c_b64 = _b64url(json.dumps(claims, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    signing_input = f"{h_b64}.{c_b64}"
    digest = sha256_hex(signing_input)
    sig = sign_ed25519(digest, signing_key)
    return HandoffToken(
        iss_agent_id=iss_agent_id,
        iss_run_id=iss_run_id,
        handoff_node_id=handoff_node_id,
        handoff_node_hash=handoff_node_hash,
        to_agent_id=to_agent_id,
        iat=iat_ms,
        exp=exp,
        nonce=n,
        _signing_input=signing_input,
        _signature=sig,
    )
