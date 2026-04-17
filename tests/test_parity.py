"""Cross-language parity: the Python SDK MUST produce a byte-identical
canonical form and hash as the TypeScript SDK for a fixed payload. The
expected value here is generated once and pinned in both test suites
(Python: this file; TS: src/resources/parity.test.ts). A drift means
signatures issued by one SDK won't verify under the other."""

from invariance import hash_node_payload, stable_stringify

FIXTURE_PAYLOAD = {
    "id": "node_0000000000000001",
    "run_id": "run_test",
    "agent_id": "agent_test",
    "parent_id": None,
    "action_type": "tool_call",
    "input": {"query": "refund"},
    "output": {"answer": "ok"},
    "error": None,
    "metadata": {"k": "v"},
    "custom_fields": {"trace": "abc"},
    "timestamp": 1775900000000,
    "duration_ms": 25,
    "previous_hashes": ["aa", "bb"],
}

EXPECTED_CANONICAL = (
    '{"action_type":"tool_call","agent_id":"agent_test",'
    '"custom_fields":{"trace":"abc"},"duration_ms":25,"error":null,'
    '"id":"node_0000000000000001","input":{"query":"refund"},'
    '"metadata":{"k":"v"},"output":{"answer":"ok"},"parent_id":null,'
    '"previous_hashes":["aa","bb"],"run_id":"run_test",'
    '"timestamp":1775900000000}'
)

EXPECTED_HASH = "8d9d5be0c9b7113508a613049362530dbbd9779f33b6ac2f32069b15853a93b1"


def test_canonical_form_matches_pinned():
    assert stable_stringify(FIXTURE_PAYLOAD) == EXPECTED_CANONICAL


def test_hash_matches_pinned():
    assert hash_node_payload(FIXTURE_PAYLOAD) == EXPECTED_HASH
