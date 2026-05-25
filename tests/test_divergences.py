"""Tests for DivergencesResource (sync)."""

from __future__ import annotations

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


def test_divergences_list_passes_filters():
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["path"] = request.url.path
        seen["query"] = dict(request.url.params)
        return httpx.Response(200, json={"data": [], "next_cursor": None})

    inv = _inv_with_handler(handler)
    out = inv.divergences.list(
        run_id="run_1", kind="policy", severity="high", status="open", limit=10
    )
    assert seen["method"] == "GET"
    assert seen["path"] == "/v1/divergences"
    assert seen["query"] == {
        "run_id": "run_1",
        "kind": "policy",
        "severity": "high",
        "status": "open",
        "limit": "10",
    }
    assert out == {"data": [], "next_cursor": None}


def test_divergences_get_unwraps():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/divergences/dv_1"
        return httpx.Response(200, json={"divergence": {"id": "dv_1", "status": "open"}})

    inv = _inv_with_handler(handler)
    out = inv.divergences.get("dv_1")
    assert out == {"id": "dv_1", "status": "open"}


def test_divergences_update_patches_status():
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["path"] = request.url.path
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"divergence": {"id": "dv_1", "status": "dismissed"}})

    inv = _inv_with_handler(handler)
    out = inv.divergences.update("dv_1", status="dismissed")
    assert seen["method"] == "PATCH"
    assert seen["path"] == "/v1/divergences/dv_1"
    assert seen["body"] == {"status": "dismissed"}
    assert out["status"] == "dismissed"
