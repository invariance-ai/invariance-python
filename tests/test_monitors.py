import json

import httpx
import pytest

from invariance import (
    Invariance,
    MonitorSpec,
    action,
    compile_monitor,
    define_node_type,
    evaluator,
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


# ── compile_monitor → backend CreateMonitorRequest ─────────────────────────


def test_compile_field_contains_maps_to_keyword_evaluator():
    d = compile_monitor(
        MonitorSpec(
            name="pii",
            on=on.node(action_type="tool.use"),
            when=rule.field_contains("output", "ssn"),
            do=action.emit_signal(severity="high", title="PII", type="pii"),
        )
    )
    assert d == {
        "name": "pii",
        "evaluator": {
            "type": "keyword",
            "field": "output",
            "keywords": ["ssn"],
            "case_sensitive": False,
        },
        "severity": "high",
        "signal_type": "pii",
    }


def test_compile_numeric_maps_to_threshold_evaluator():
    BillingCharge = define_node_type("billing_charge")
    d = compile_monitor(
        MonitorSpec(
            name="expensive",
            on=on.node(type=BillingCharge.type),
            when=rule.numeric("custom_fields.amount_cents", "gt", 10000),
            do=action.emit_signal(severity="medium", title="big"),
        )
    )
    assert d["evaluator"] == {
        "type": "threshold",
        "field": "custom_fields.amount_cents",
        "operator": ">",
        "value": 10000,
    }
    assert d["severity"] == "medium"


def test_compile_create_finding_sets_creates_review():
    d = compile_monitor(
        MonitorSpec(
            name="x",
            on=on.node(action_type="tool.use"),
            when=rule.field_contains("output", "bad"),
            do=action.create_finding(severity="critical", title="Bad", type="bad"),
        )
    )
    assert d["creates_review"] is True
    assert d["signal_type"] == "bad"
    assert d["severity"] == "critical"


def test_compile_rejects_unsupported_judge_llm():
    with pytest.raises(NotImplementedError, match="judge_llm"):
        compile_monitor(
            MonitorSpec(
                name="j",
                on=on.run(agent_id="agt_1"),
                when=evaluator.judge_llm(model="claude-sonnet-4-6", rubric="ok?"),
                do=action.emit_signal(severity="low", title="t"),
            )
        )


def test_compile_rejects_rule_composition():
    with pytest.raises(NotImplementedError, match="composition"):
        compile_monitor(
            MonitorSpec(
                name="combo",
                on=on.agent("agt_x"),
                when=rule.any_(
                    rule.field_equals("status", "error"), rule.exists("error")
                ),
                do=action.emit_signal(severity="low", title="t"),
            )
        )


def test_node_type_stamps_type_field():
    Charge = define_node_type("charge")
    n = Charge.node("tool.use", custom_fields={"amount": 10})
    assert n["type"] == "charge"
    assert n["custom_fields"] == {"amount": 10}


def test_monitors_create_posts_backend_shape():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"monitor": {"id": "mon_1"}})

    inv = _client_with_handler(handler)
    inv.monitors.create(
        MonitorSpec(
            name="x",
            on=on.node(type="charge"),
            when=rule.numeric("custom_fields.amount", "gt", 100),
            do=action.emit_signal(severity="low", title="big"),
        )
    )
    assert seen["path"] == "/v1/monitors"
    body = seen["body"]
    assert body["name"] == "x"
    assert body["evaluator"]["type"] == "threshold"
    assert body["evaluator"]["field"] == "custom_fields.amount"
    assert body["evaluator"]["operator"] == ">"
    assert body["severity"] == "low"


# ── Resource surface: update / pause / resume / list ───────────────────────


def test_monitors_list_forwards_params():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["params"] = dict(request.url.params)
        return httpx.Response(200, json={"data": [], "next_cursor": None})

    inv = _client_with_handler(handler)
    inv.monitors.list(limit=25, status="active")
    assert seen["path"] == "/v1/monitors"
    assert seen["params"]["limit"] == "25"
    assert seen["params"]["status"] == "active"


def test_monitors_update_patches_name_and_severity():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["path"] = request.url.path
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"monitor": {"id": "mon_1"}})

    inv = _client_with_handler(handler)
    inv.monitors.update("mon_1", name="renamed", severity="critical")
    assert seen["method"] == "PUT"
    assert seen["path"] == "/v1/monitors/mon_1"
    assert seen["body"] == {"name": "renamed", "severity": "critical"}


def test_monitors_pause_and_resume_delegate_to_update():
    calls: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append({"method": request.method, "body": json.loads(request.content)})
        return httpx.Response(200, json={"monitor": {"id": "mon_1"}})

    inv = _client_with_handler(handler)
    inv.monitors.pause("mon_1")
    inv.monitors.resume("mon_1")
    assert calls[0]["body"] == {"status": "paused"}
    assert calls[1]["body"] == {"status": "active"}
