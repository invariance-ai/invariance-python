"""Tests for WorkflowObservabilityResource (sync)."""

from __future__ import annotations

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


def test_workflow_observability_list():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/v1/workflow-observability"
        return httpx.Response(200, json={"data": [{"workflow_key": "wf.a"}], "next_cursor": None})

    inv = _inv_with_handler(handler)
    out = inv.workflow_observability.list()
    assert out == {"data": [{"workflow_key": "wf.a"}], "next_cursor": None}


def test_workflow_observability_get_unwraps_rollup():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/workflow-observability/wf.a"
        return httpx.Response(200, json={"rollup": {"workflow_key": "wf.a", "execution_count": 3}})

    inv = _inv_with_handler(handler)
    out = inv.workflow_observability.get("wf.a")
    assert out == {"workflow_key": "wf.a", "execution_count": 3}


def test_workflow_observability_executions():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/workflow-observability/wf.a/executions"
        return httpx.Response(200, json={"data": [{"case_id": "c_1"}], "next_cursor": None})

    inv = _inv_with_handler(handler)
    out = inv.workflow_observability.executions("wf.a")
    assert out["data"] == [{"case_id": "c_1"}]
