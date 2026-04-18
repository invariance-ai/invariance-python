import httpx

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


def test_compile_session_rule():
    d = compile_monitor(
        MonitorSpec(
            name="pii",
            on=on.session(id="sess_1"),
            when=rule.field_contains("output", "ssn"),
            do=action.create_finding(severity="high", title="PII"),
        )
    )
    assert d["target"] == "session"
    assert d["target_match"]["filters"] == [
        {"field": "session_id", "operator": "eq", "value": "sess_1"}
    ]
    assert d["rules"] == [
        {"kind": "field_match", "field": "output", "operator": "contains", "value": "ssn"}
    ]
    assert d["actions"][0]["type"] == "create_finding"
    assert d["signal"]["severity"] == "high"


def test_compile_node_type_numeric():
    BillingCharge = define_node_type("billing_charge")
    d = compile_monitor(
        MonitorSpec(
            name="expensive",
            on=on.node(type=BillingCharge.type),
            when=rule.numeric("custom_fields.amount_cents", "gt", 10000),
            do=action.notify("slack", "#billing"),
        )
    )
    assert {"field": "type", "operator": "eq", "value": "billing_charge"} in d["target_match"][
        "filters"
    ]
    assert d["rules"][0]["kind"] == "numeric_threshold"
    assert d["rules"][0]["value"] == 10000


def test_compile_llm_judge():
    d = compile_monitor(
        MonitorSpec(
            name="judge",
            on=on.run(agent_id="agt_1"),
            when=evaluator.judge_llm(model="claude-sonnet-4-6", rubric="ok?"),
            do=action.emit_signal(severity="medium", title="bad"),
        )
    )
    assert d["evaluator"]["type"] == "judge_llm"
    assert d["evaluator"]["model"] == "claude-sonnet-4-6"
    assert d["rules"] == []


def test_compile_any_of_rules():
    d = compile_monitor(
        MonitorSpec(
            name="combo",
            on=on.agent("agt_x"),
            when=rule.any_(rule.field_equals("status", "error"), rule.exists("error")),
            do=action.mark("reviewed"),
        )
    )
    assert d["match"] == "any"
    assert len(d["rules"]) == 2
    assert d["actions"][0] == {"type": "mark_object", "label": "reviewed"}


def test_node_type_stamps_type_field():
    Charge = define_node_type("charge")
    n = Charge.node("tool.use", custom_fields={"amount": 10})
    assert n["type"] == "charge"
    assert n["custom_fields"] == {"amount": 10}


def test_monitors_create_posts_compiled_definition():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        import json

        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "monitor": {
                    "id": "mon_1",
                    "name": "x",
                    "status": "active",
                    "definition": {},
                    "triggers_count": 0,
                    "created_at": "t",
                }
            },
        )

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
    assert seen["body"]["name"] == "x"
    assert seen["body"]["definition"]["target"] == "trace_node"
    assert seen["body"]["definition"]["rules"][0]["kind"] == "numeric_threshold"
