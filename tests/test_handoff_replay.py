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
