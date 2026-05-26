"""Cross-language proof parity (XR-002).

The Python SDK MUST produce a byte-identical canonical form, hash, AND
Ed25519 signature as the TypeScript SDK for a fixed payload and key. The
golden values live in a committed JSON fixture that is byte-identical in
both repos (Python: tests/fixtures/proof_parity_golden.json; TS:
src/resources/fixtures/proof-parity.golden.json). This test re-derives every
value from ``payload`` and asserts it equals the pinned golden, then checks
the signature verifies. A drift means signatures issued by one SDK won't
verify under the other.
"""

import json
from pathlib import Path

from invariance import (
    get_public_key,
    hash_node_payload,
    sign_ed25519,
    stable_stringify,
    verify_ed25519,
)

_GOLDEN = json.loads(
    (Path(__file__).parent / "fixtures" / "proof_parity_golden.json").read_text()
)


def test_canonical_form_matches_pinned_golden():
    assert stable_stringify(_GOLDEN["payload"]) == _GOLDEN["canonical"]


def test_hash_matches_pinned_golden():
    assert hash_node_payload(_GOLDEN["payload"]) == _GOLDEN["hash"]


def test_public_key_derives_from_pinned_signing_key():
    assert get_public_key(_GOLDEN["signing_key_hex"]) == _GOLDEN["public_key_hex"]


def test_ed25519_signature_over_hash_matches_pinned_golden():
    # Ed25519 (RFC 8032) is deterministic: PyNaCl (Python) and @noble/ed25519
    # (TS) must produce the identical signature for this key + hash.
    assert sign_ed25519(_GOLDEN["hash"], _GOLDEN["signing_key_hex"]) == _GOLDEN["signature_hex"]


def test_pinned_signature_verifies_under_pinned_public_key():
    assert verify_ed25519(
        _GOLDEN["hash"], _GOLDEN["signature_hex"], _GOLDEN["public_key_hex"]
    )
