"""Tests for ProofsResource, FindingsResource, ReviewsResource."""

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
