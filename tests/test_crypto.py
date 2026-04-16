from invariance import (
    generate_keypair,
    get_public_key,
    sign_ed25519,
    verify_ed25519,
    hash_node_payload,
    stable_stringify,
)


def test_stable_stringify_sorts_keys_preserves_arrays():
    assert (
        stable_stringify({"b": 1, "a": {"d": 4, "c": 3}, "e": [{"y": 2, "x": 1}]})
        == '{"a":{"c":3,"d":4},"b":1,"e":[{"x":1,"y":2}]}'
    )


def test_stable_stringify_null_value():
    assert stable_stringify({"a": 1, "c": None}) == '{"a":1,"c":null}'


def test_hash_node_payload_key_order_invariant():
    a = {
        "id": "node_1",
        "session_id": "s",
        "agent_id": "a",
        "parent_id": None,
        "action_type": "t",
        "input": {"a": 1, "b": 2},
        "output": None,
        "error": None,
        "metadata": {"k": "v"},
        "custom_fields": {},
        "timestamp": 100,
        "duration_ms": None,
        "previous_hashes": ["aa"],
    }
    # Reverse insertion order but same content.
    b = dict(reversed(list(a.items())))
    assert hash_node_payload(a) == hash_node_payload(b)


def test_hash_changes_with_custom_fields():
    base = {
        "id": "n",
        "session_id": "s",
        "agent_id": "a",
        "parent_id": None,
        "action_type": "t",
        "input": None,
        "output": None,
        "error": None,
        "metadata": {},
        "custom_fields": {"tenant": "a"},
        "timestamp": 1,
        "duration_ms": None,
        "previous_hashes": [],
    }
    mutated = {**base, "custom_fields": {"tenant": "b"}}
    assert hash_node_payload(base) != hash_node_payload(mutated)


def test_ed25519_roundtrip():
    sk, pk = generate_keypair()
    assert get_public_key(sk) == pk

    msg = "deadbeef" * 8
    sig = sign_ed25519(msg, sk)
    assert len(sig) == 128
    assert verify_ed25519(msg, sig, pk) is True

    tampered = "c" * 64
    assert verify_ed25519(tampered, sig, pk) is False
