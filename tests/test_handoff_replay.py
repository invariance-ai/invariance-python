"""Tests for multi-agent handoff + fork + replay gating."""

import json
import os

import httpx
import pytest

from invariance import Invariance
from invariance.replay import reproducible


def _inv_with_capture(features: dict | None = None):
    calls: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        body = request.content.decode() if request.content else ""
        parsed = json.loads(body) if body else None
        calls.append({"method": request.method, "path": path, "body": parsed})

        if request.method == "POST" and path == "/v1/runs":
            return httpx.Response(
                200,
                json={
                    "run": {
                        "id": "run_1",
                        "agent_id": "a_1",
                        "name": (parsed or {}).get("name", ""),
                        "status": "open",
                        "replay_seed": (parsed or {}).get("replay_seed"),
                    }
                },
            )
        if request.method == "POST" and path.endswith("/fork"):
            return httpx.Response(
                200,
                json={
                    "run": {
                        "id": "run_fork_1",
                        "agent_id": "a_1",
                        "name": "forked",
                        "status": "open",
                        "parent_run_id": "run_1",
                        "fork_point_node_id": (parsed or {}).get("from_node_id"),
                    }
                },
            )
        if request.method == "POST" and path == "/v1/nodes":
            items = parsed if isinstance(parsed, list) else [parsed]
            data = [{**item, "hash": f"h_{i}"} for i, item in enumerate(items)]
            return httpx.Response(200, json={"data": data})
        if request.method == "PATCH":
            return httpx.Response(200, json={"run": {"id": "run_1", "status": "completed"}})
        return httpx.Response(404, json={"error": {"code": "nf", "message": "nf"}})

    transport = httpx.MockTransport(handler)
    inv = Invariance(api_key="inv_test_abc", api_url="http://test.local", features=features)
    inv._http._client = httpx.Client(
        base_url="http://test.local",
        headers={"Authorization": "Bearer inv_test_abc"},
        transport=transport,
    )
    return inv, calls


def test_step_carries_handoff_fields():
    inv, calls = _inv_with_capture()
    with inv.runs.start() as run:
        with run.step(
            "delegate",
            handoff_from="planner",
            handoff_to="executor",
            handoff_reason="needs tool access",
        ):
            pass

    node_posts = [c for c in calls if c["path"] == "/v1/nodes"]
    nodes = node_posts[0]["body"]
    n = nodes[0] if isinstance(nodes, list) else nodes
    assert n["handoff_from"] == "planner"
    assert n["handoff_to"] == "executor"
    assert n["handoff_reason"] == "needs tool access"


def test_run_handoff_helper_emits_typed_node():
    inv, calls = _inv_with_capture()
    with inv.runs.start() as run:
        run.handoff("executor", message={"task": "fetch docs"}, reason="specialist")

    node_posts = [c for c in calls if c["path"] == "/v1/nodes"]
    nodes = node_posts[0]["body"]
    n = nodes[0] if isinstance(nodes, list) else nodes
    assert n["action_type"] == "handoff"
    assert n["handoff_to"] == "executor"
    assert n["handoff_reason"] == "specialist"
    assert n["input"] == {"message": {"task": "fetch docs"}}


def test_replay_seed_rejected_without_feature_flag():
    inv, _ = _inv_with_capture()
    with pytest.raises(ValueError, match="INVARIANCE_FEATURE_REPLAY"):
        inv.runs.start(replay_seed="s1")


def test_fork_rejected_without_feature_flag():
    inv, _ = _inv_with_capture()
    with pytest.raises(ValueError, match="INVARIANCE_FEATURE_REPLAY"):
        inv.runs.fork("run_1", from_node_id="n_1")


def test_fork_succeeds_with_feature_flag():
    inv, calls = _inv_with_capture(features={"replay": True})
    forked = inv.runs.fork("run_1", from_node_id="n_3", name="replay attempt")
    assert forked.run_id == "run_fork_1"
    fork_posts = [c for c in calls if c["path"].endswith("/fork")]
    assert fork_posts[0]["body"]["from_node_id"] == "n_3"
    assert fork_posts[0]["body"]["name"] == "replay attempt"


def test_reproducible_is_noop_when_disabled(monkeypatch):
    monkeypatch.delenv("INVARIANCE_FEATURE_REPLAY", raising=False)
    ran = {"count": 0}

    @reproducible(seed="s1")
    def f():
        import random
        ran["count"] += 1
        return random.random()

    # No seeding → two calls diverge (almost certainly).
    a, b = f(), f()
    assert ran["count"] == 2
    # Can't assert inequality deterministically but seed wasn't applied.


def test_reproducible_seeds_prng_when_enabled(monkeypatch):
    monkeypatch.setenv("INVARIANCE_FEATURE_REPLAY", "true")

    @reproducible(seed="stable-seed")
    def f():
        import random
        return [random.random() for _ in range(3)]

    assert f() == f()


def test_pricing_table_known_model():
    from invariance.providers.pricing import price_call
    cost = price_call("gpt-4o-mini", input_tokens=1000, output_tokens=500)
    # 1000 * 0.00015/1000 + 500 * 0.0006/1000 = 0.00015 + 0.0003 = 0.00045
    assert cost == pytest.approx(0.00045, abs=1e-6)


def test_pricing_unknown_model_zero():
    from invariance.providers.pricing import price_call
    assert price_call("mystery-model-xyz", 1000, 500) == 0.0


# ── Cryptographic handoff attestation ─────────────────────────────────────


def test_handoff_fields_are_in_signed_payload():
    """Tampering with handoff_to on the wire must invalidate the signature."""
    from invariance._internal import build_node_body
    from invariance.crypto import generate_keypair, hash_node_payload, verify_ed25519

    priv, pub = generate_keypair()
    body_a, _ = build_node_body(
        run_id="run_1",
        agent_id="planner",
        last_hash=None,
        signing_key=priv,
        id="node_1",
        action_type="handoff",
        type="handoff",
        input=None,
        output=None,
        error=None,
        metadata=None,
        custom_fields=None,
        parent_id=None,
        timestamp=1_700_000_000_000,
        duration_ms=0,
        handoff_from="planner",
        handoff_to="executor",
        handoff_reason="needs tools",
    )
    # Recompute the intended payload and verify round-trip.
    payload_ok = {
        "id": "node_1",
        "run_id": "run_1",
        "agent_id": "planner",
        "parent_id": None,
        "action_type": "handoff",
        "input": None,
        "output": None,
        "error": None,
        "metadata": {},
        "custom_fields": {},
        "timestamp": 1_700_000_000_000,
        "duration_ms": 0,
        "previous_hashes": [],
        "handoff_from": "planner",
        "handoff_to": "executor",
        "handoff_reason": "needs tools",
    }
    assert verify_ed25519(hash_node_payload(payload_ok), body_a["signature"], pub)

    # Tampered handoff_to must no longer verify under the same signature.
    payload_tamper = dict(payload_ok, handoff_to="attacker")
    assert not verify_ed25519(hash_node_payload(payload_tamper), body_a["signature"], pub)


def test_handoff_returns_token_when_signed():
    """run.handoff() returns a signed token referencing the handoff node."""
    from invariance.crypto import generate_keypair

    priv, _pub = generate_keypair()

    calls: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        body = json.loads(request.content) if request.content else None
        calls.append({"method": request.method, "path": path, "body": body})
        if request.method == "GET" and path == "/v1/agents/me":
            return httpx.Response(200, json={"agent": {"id": "planner", "name": "planner", "public_key": None, "project_id": "p", "created_at": "2024-01-01T00:00:00Z"}})
        if request.method == "POST" and path == "/v1/runs":
            return httpx.Response(200, json={"run": {"id": "run_1", "agent_id": "planner", "status": "open"}})
        if request.method == "POST" and path == "/v1/nodes":
            items = body if isinstance(body, list) else [body]
            return httpx.Response(200, json={"data": [{**item, "hash": item.get("id", "h")} for item in items]})
        if request.method == "PATCH":
            return httpx.Response(200, json={"run": {"id": "run_1", "status": "completed"}})
        return httpx.Response(404, json={"error": {"code": "nf", "message": "nf"}})

    inv = Invariance(api_key="inv_test_x", api_url="http://t.local", signing_key=priv)
    inv._http._client = httpx.Client(
        base_url="http://t.local",
        headers={"Authorization": "Bearer inv_test_x"},
        transport=httpx.MockTransport(handler),
    )

    with inv.runs.start() as run:
        run._session["agent_id"] = "planner"
        token = run.handoff("executor", reason="specialist")

    assert token is not None
    encoded = token.encode()
    assert encoded.count(".") == 2
    assert token.to_agent_id == "executor"
    assert token.iss_agent_id == "planner"

    # Buffer was flushed on handoff so the handoff node is already POSTed.
    node_posts = [c for c in calls if c["path"] == "/v1/nodes"]
    assert node_posts, "handoff node must be flushed before token is issued"
    flushed = node_posts[0]["body"]
    flushed_list = flushed if isinstance(flushed, list) else [flushed]
    assert any(n.get("type") == "handoff" for n in flushed_list)


def test_handoff_returns_none_when_unsigned():
    inv, _ = _inv_with_capture()
    with inv.runs.start() as run:
        token = run.handoff("executor")
    assert token is None
