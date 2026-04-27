"""Tests for NodeTypesResource (sync + async)."""

from __future__ import annotations

import asyncio
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


def _async_inv_with_handler(handler):
    transport = httpx.MockTransport(handler)
    inv = AsyncInvariance(api_key="inv_test", api_url="http://test.local")
    inv._http._client = httpx.AsyncClient(
        base_url="http://test.local",
        headers={"Authorization": "Bearer inv_test"},
        transport=transport,
    )
    return inv


def test_node_types_list_hits_expected_path():
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["path"] = request.url.path
        return httpx.Response(
            200,
            json={"data": [{"id": "nt_1", "name": "billing_charge"}]},
        )

    inv = _inv_with_handler(handler)
    res = inv.node_types.list()
    assert seen["method"] == "GET"
    assert seen["path"] == "/v1/node-types"
    assert res == [{"id": "nt_1", "name": "billing_charge"}]


def test_node_types_register_posts_body_and_unwraps():
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["path"] = request.url.path
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={"node_type": {"id": "nt_1", "name": "billing_charge"}},
        )

    inv = _inv_with_handler(handler)
    out = inv.node_types.register(
        "billing_charge",
        display_name="Billing Charge",
        custom_fields_schema={"required": ["user_id"], "field_types": {"user_id": "string"}},
        aggregation_hints={"key_field": "user_id"},
    )
    assert seen["method"] == "POST"
    assert seen["path"] == "/v1/node-types"
    assert seen["body"] == {
        "name": "billing_charge",
        "display_name": "Billing Charge",
        "custom_fields_schema": {
            "required": ["user_id"],
            "field_types": {"user_id": "string"},
        },
        "aggregation_hints": {"key_field": "user_id"},
    }
    assert out == {"id": "nt_1", "name": "billing_charge"}


def test_node_types_register_minimal_omits_optional_keys():
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"node_type": {"id": "nt_2", "name": "x"}})

    inv = _inv_with_handler(handler)
    inv.node_types.register("x")
    assert seen["body"] == {"name": "x"}


def test_async_node_types_register_and_list():
    calls: list = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            calls.append({"method": request.method, "path": request.url.path,
                          "body": json.loads(request.content)})
            return httpx.Response(200, json={"node_type": {"id": "nt_1", "name": "x"}})
        calls.append({"method": request.method, "path": request.url.path})
        return httpx.Response(200, json={"data": [{"id": "nt_1", "name": "x"}]})

    async def run() -> None:
        inv = _async_inv_with_handler(handler)
        out = await inv.node_types.register("x", display_name="X")
        assert out == {"id": "nt_1", "name": "x"}
        listed = await inv.node_types.list()
        assert listed == [{"id": "nt_1", "name": "x"}]
        await inv.aclose()

    asyncio.run(run())
    assert calls[0]["path"] == "/v1/node-types"
    assert calls[0]["body"] == {"name": "x", "display_name": "X"}
    assert calls[1] == {"method": "GET", "path": "/v1/node-types"}
