"""Tests for ProofsResource, FindingsResource, ReviewsResource, NodeTypesResource."""

import json

import httpx

from invariance import AsyncInvariance, Invariance


def _inv_with_handler(handler):
    transport = httpx.MockTransport(handler)
    inv = Invariance(api_key="inv_test", api_url="http://test.local")
    inv._http._client = httpx.Client(
        base_url="http://test.local",
        headers={"Authorization": "Bearer inv_test"},
        transport=transport,
    )
    return inv


def test_proofs_verify_run_hits_expected_path():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/v1/runs/run_1/verify"
        return httpx.Response(
            200,
            json={"run_id": "run_1", "valid": True, "node_count": 3, "head_hash": "h", "first_invalid_node_id": None, "reason": None},
        )

    inv = _inv_with_handler(handler)
    res = inv.proofs.verify_run("run_1")
    assert res["valid"] is True
    assert res["node_count"] == 3


def test_findings_update_posts_status():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["path"] = request.url.path
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"finding": {"id": "f_1", "status": "resolved"}})

    inv = _inv_with_handler(handler)
    f = inv.findings.update("f_1", status="resolved")
    assert seen["method"] == "PATCH"
    assert seen["path"] == "/v1/findings/f_1"
    assert seen["body"] == {"status": "resolved"}
    assert f["status"] == "resolved"


def test_findings_list_params():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["params"] = dict(request.url.params)
        return httpx.Response(200, json={"data": [], "next_cursor": None})

    inv = _inv_with_handler(handler)
    inv.findings.list(limit=5, cursor="c_1")
    assert seen["params"] == {"cursor": "c_1", "limit": "5"}


def test_reviews_claim_and_resolve():
    calls: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append({"method": request.method, "path": request.url.path, "body": json.loads(request.content)})
        return httpx.Response(200, json={"review": {"id": "rv_1"}, "finding": {"id": "f_1"}})

    inv = _inv_with_handler(handler)
    inv.reviews.claim("rv_1", notes="mine")
    inv.reviews.resolve("rv_1", decision="passed", notes="looks ok")
    assert calls[0]["body"] == {"status": "claimed", "notes": "mine"}
    assert calls[1]["body"] == {"decision": "passed", "notes": "looks ok"}


# ── NodeTypesResource (parity with TS inv.nodeTypes) ────────────────────────


_NODE_TYPE_FIXTURE = {
    "id": "nt_1",
    "project_id": "proj_1",
    "name": "billing_charge",
    "display_name": "Billing Charge",
    "custom_fields_schema": {"required": ["user_id"]},
    "aggregation_hints": {"key_field": "user_id"},
    "created_at": "2026-04-24T00:00:00Z",
    "updated_at": "2026-04-24T00:00:00Z",
}


def test_node_types_list_hits_v1_endpoint():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/v1/node-types"
        return httpx.Response(200, json={"data": [_NODE_TYPE_FIXTURE]})

    inv = _inv_with_handler(handler)
    res = inv.node_types.list()
    assert len(res) == 1
    assert res[0]["name"] == "billing_charge"


def test_node_types_register_posts_body():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/v1/node-types"
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"node_type": _NODE_TYPE_FIXTURE})

    inv = _inv_with_handler(handler)
    out = inv.node_types.register(
        "billing_charge",
        display_name="Billing Charge",
        custom_fields_schema={"required": ["user_id"]},
    )
    assert out["id"] == "nt_1"
    assert captured["body"] == {
        "name": "billing_charge",
        "display_name": "Billing Charge",
        "custom_fields_schema": {"required": ["user_id"]},
    }


def test_async_invariance_exposes_node_types():
    inv = AsyncInvariance(api_key="inv_test", api_url="http://test.local")
    assert hasattr(inv, "node_types")
    assert callable(getattr(inv.node_types, "list", None))
    assert callable(getattr(inv.node_types, "register", None))
