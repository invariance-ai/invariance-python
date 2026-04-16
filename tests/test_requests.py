import httpx
import pytest

from invariance import Invariance, InvarianceApiError
from invariance.client import HttpClient


def _client_with_handler(handler):
    transport = httpx.MockTransport(handler)
    inv = Invariance(api_key="inv_test_abc", api_url="http://test.local")
    inv._http._client = httpx.Client(
        base_url="http://test.local",
        headers={"Authorization": "Bearer inv_test_abc"},
        transport=transport,
    )
    return inv


def test_auth_header_sent():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers.get("authorization")
        return httpx.Response(200, json={"agent": {"id": "a", "name": "x"}})

    inv = _client_with_handler(handler)
    inv.agents.me()
    assert seen["auth"] == "Bearer inv_test_abc"


def test_runs_start_path_and_body():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["path"] = request.url.path
        seen["body"] = request.content.decode() or "{}"
        return httpx.Response(
            200,
            json={"session": {"id": "sess_1", "name": "demo", "status": "open"}},
        )

    inv = _client_with_handler(handler)
    run = inv.runs.start(name="demo")
    assert seen["method"] == "POST"
    assert seen["path"] == "/v1/sessions"
    assert '"name":"demo"' in seen["body"].replace(" ", "")
    assert run.session_id == "sess_1"


def test_node_write_path_and_body():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["path"] = request.url.path
        seen["body"] = request.content.decode()
        return httpx.Response(200, json={"data": [{"id": "n_1", "action_type": "tool_call"}]})

    inv = _client_with_handler(handler)
    # Use Run.node() which is the public API
    from invariance.runs import Run

    run = Run(inv._http, {"id": "sess_1", "agent_id": "a_1", "name": "demo", "status": "open"})
    result = run.node(action_type="tool_call", input={"a": 1}, output={"b": 2})
    assert seen["method"] == "POST"
    assert seen["path"] == "/v1/nodes"
    assert '"session_id":"sess_1"' in seen["body"].replace(" ", "")
    assert '"action_type":"tool_call"' in seen["body"].replace(" ", "")
    assert result["id"] == "n_1"


def test_backend_error_preserved():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            403,
            json={
                "error": {
                    "code": "forbidden",
                    "message": "no access",
                    "details": {"agent": "other"},
                    "request_id": "req_42",
                }
            },
        )

    inv = _client_with_handler(handler)
    with pytest.raises(InvarianceApiError) as ei:
        inv.agents.me()
    assert ei.value.status == 403
    assert ei.value.code == "forbidden"
    assert ei.value.details == {"agent": "other"}
    assert ei.value.request_id == "req_42"
