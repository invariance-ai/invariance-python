import json

import httpx

from invariance import (
    Invariance,
    MonitorSpec,
    action,
    compile_monitor,
    define_signal_type,
    on,
    rule,
)


def _client_with_handler(handler):
    transport = httpx.MockTransport(handler)
    inv = Invariance(api_key="inv_test", api_url="http://test.local")
    inv._http._client = httpx.Client(
        base_url="http://test.local",
        headers={"Authorization": "Bearer inv_test"},
        transport=transport,
    )
    return inv


def test_define_signal_type_shape():
    Dangerous = define_signal_type(
        "dangerous_output",
        severity="high",
        title="Dangerous output",
    )
    spec = Dangerous.signal(data={"reason": "keyword"})
    assert spec == {
        "type": "dangerous_output",
        "severity": "high",
        "title": "Dangerous output",
        "data": {"reason": "keyword"},
    }


def test_signal_type_allows_overrides():
    T = define_signal_type("x", severity="low", title="T", message="m")
    spec = T.signal(severity="critical", title="override", data={"k": 1})
    assert spec["severity"] == "critical"
    assert spec["title"] == "override"
    assert spec["message"] == "m"
    assert spec["type"] == "x"


def test_signals_emit_posts_body():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            201,
            json={
                "signal": {
                    "id": "signal_1",
                    "type": captured["body"].get("type"),
                    **captured["body"],
                }
            },
        )

    inv = _client_with_handler(handler)
    T = define_signal_type("danger", severity="high", title="Danger")
    sig = inv.signals.emit(**T.signal(data={"reason": "x"}))
    assert captured["path"] == "/v1/signals"
    assert captured["body"]["type"] == "danger"
    assert captured["body"]["severity"] == "high"
    assert captured["body"]["data"] == {"reason": "x"}
    assert sig["id"] == "signal_1"


def test_run_signal_auto_attaches_last_node_id():
    captured: dict = {"calls": []}

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/v1/runs" and request.method == "POST":
            return httpx.Response(
                201,
                json={"run": {"id": "run_1", "agent_id": "agent_1", "name": "t", "status": "open"}},
            )
        if path == "/v1/nodes" and request.method == "POST":
            bodies = json.loads(request.content)
            if not isinstance(bodies, list):
                bodies = [bodies]
            data = [{**b, "hash": f"h_{i}"} for i, b in enumerate(bodies)]
            return httpx.Response(201, json={"data": data})
        if path.startswith("/v1/runs/") and request.method == "PATCH":
            return httpx.Response(
                200,
                json={"run": {"id": "run_1", "agent_id": "agent_1", "name": "t", "status": "completed"}},
            )
        if path == "/v1/signals" and request.method == "POST":
            body = json.loads(request.content)
            captured["calls"].append(body)
            return httpx.Response(201, json={"signal": {"id": "signal_1", **body}})
        return httpx.Response(404)

    inv = _client_with_handler(handler)
    Dangerous = define_signal_type("dangerous", severity="high", title="D")
    with inv.runs.start(name="t") as run:
        with run.step("tool.use") as s:
            s.output = {"answer": "x"}
        sig = run.signal(Dangerous.signal(data={"r": 1}))

    body = captured["calls"][0]
    assert body["type"] == "dangerous"
    assert body["run_id"] == "run_1"
    assert body["node_id"].startswith("node_")
    assert body["data"] == {"r": 1}
    assert sig["id"] == "signal_1"


def test_signals_resolve_patches():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["path"] = request.url.path
        return httpx.Response(
            200, json={"signal": {"id": "signal_9", "status": "resolved"}}
        )

    inv = _client_with_handler(handler)
    got = inv.signals.resolve("signal_9")
    assert captured["method"] == "PATCH"
    assert captured["path"] == "/v1/signals/signal_9/resolve"
    assert got["status"] == "resolved"


def test_run_signal_requires_spec_dict():
    import pytest

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404)

    inv = _client_with_handler(handler)
    from invariance.runs import Run

    run = Run(inv._http, {"id": "run_1", "agent_id": "a_1", "name": "t", "status": "open"})
    with pytest.raises(ValueError, match="severity and title"):
        run.signal({"severity": "high"})


def test_monitor_emit_signal_compiles_signal_type():
    d = compile_monitor(
        MonitorSpec(
            name="x",
            on=on.node(action_type="tool.use"),
            when=rule.field_contains("output", "danger"),
            do=action.emit_signal(severity="high", title="Danger", type="dangerous"),
        )
    )
    assert d["actions"][0]["signal_type"] == "dangerous"
    assert d["signal"]["type"] == "dangerous"
