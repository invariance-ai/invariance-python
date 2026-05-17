import json

import httpx

from invariance import Invariance


def _inv_with_handler(handler):
    transport = httpx.MockTransport(handler)
    inv = Invariance(api_key="inv_test", api_url="http://test.local")
    inv._http._client = httpx.Client(
        base_url="http://test.local",
        headers={"Authorization": "Bearer inv_test"},
        transport=transport,
    )
    return inv


def test_workflow_definitions_create_posts_typed_shape():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["path"] = request.url.path
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            201,
            json={
                "definition": {
                    "key": seen["body"]["key"],
                    "agent_id": "agent_1",
                    "display_name": seen["body"]["display_name"],
                    "description": None,
                    "expected_fields": seen["body"]["expected_fields"],
                    "expected_steps": [],
                    "allowed_outcomes": [],
                    "custom_metrics": [],
                    "created_at": "2026-01-01T00:00:00.000Z",
                    "updated_at": "2026-01-01T00:00:00.000Z",
                }
            },
        )

    inv = _inv_with_handler(handler)
    definition = inv.workflow_definitions.create(
        key="support.escalation",
        display_name="Support Escalation",
        expected_fields=[{"name": "priority", "type": "enum", "enum": ["p0", "p1"]}],
    )

    assert seen["method"] == "POST"
    assert seen["path"] == "/v1/workflow-definitions"
    assert seen["body"] == {
        "display_name": "Support Escalation",
        "expected_fields": [{"name": "priority", "type": "enum", "enum": ["p0", "p1"]}],
        "key": "support.escalation",
    }
    assert definition["key"] == "support.escalation"


def test_events_list_filters_global_events_endpoint():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["path"] = request.url.path
        seen["params"] = dict(request.url.params)
        return httpx.Response(200, json={"data": [], "next_cursor": None})

    inv = _inv_with_handler(handler)
    res = inv.events.list(
        workflow_key="support.escalation",
        actor_type="human",
        from_="2026-01-01T00:00:00Z",
        limit=5,
    )

    assert seen["method"] == "GET"
    assert seen["path"] == "/v1/events"
    assert seen["params"] == {
        "workflow_key": "support.escalation",
        "actor_type": "human",
        "from": "2026-01-01T00:00:00Z",
        "limit": "5",
    }
    assert res["data"] == []


def test_cases_create_event_and_list_events():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else None
        calls.append(
            {
                "method": request.method,
                "path": request.url.path,
                "params": dict(request.url.params),
                "body": body,
            }
        )
        if request.method == "POST":
            return httpx.Response(201, json={"event": {"id": "evt_1", **body}})
        return httpx.Response(200, json={"data": [{"id": "evt_1"}], "next_cursor": None})

    inv = _inv_with_handler(handler)
    event = inv.cases.create_event(
        "case_1",
        type="triage.started",
        actor_type="agent",
        payload={"priority": "p0"},
        evidence_refs=[{"kind": "ticket", "id": "T-1"}],
    )
    page = inv.cases.list_events("case_1", limit=10)

    assert calls[0]["method"] == "POST"
    assert calls[0]["path"] == "/v1/cases/case_1/events"
    assert calls[0]["body"] == {
        "type": "triage.started",
        "actor_type": "agent",
        "payload": {"priority": "p0"},
        "evidence_refs": [{"kind": "ticket", "id": "T-1"}],
    }
    assert event["id"] == "evt_1"
    assert calls[1]["method"] == "GET"
    assert calls[1]["path"] == "/v1/cases/case_1/events"
    assert calls[1]["params"] == {"limit": "10"}
    assert page["data"][0]["id"] == "evt_1"
