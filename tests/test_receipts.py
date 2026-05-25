"""Tests for ReceiptsResource (sync). create/create_batch require an agent key."""

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


def test_receipts_create_posts_body_and_unwraps():
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["path"] = request.url.path
        seen["body"] = json.loads(request.content)
        return httpx.Response(201, json={"receipt": {"id": "rcpt_1", "source": "stripe"}})

    inv = _inv_with_handler(handler)
    out = inv.receipts.create(
        source="stripe",
        kind="refund",
        run_id="run_1",
        external_id="re_1",
        correlation_keys={"refund_id": "re_1"},
        payload={"amount": 500},
    )
    assert seen["method"] == "POST"
    assert seen["path"] == "/v1/receipts"
    assert seen["body"] == {
        "source": "stripe",
        "kind": "refund",
        "run_id": "run_1",
        "external_id": "re_1",
        "correlation_keys": {"refund_id": "re_1"},
        "payload": {"amount": 500},
    }
    assert out == {"id": "rcpt_1", "source": "stripe"}


def test_receipts_create_batch():
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["body"] = json.loads(request.content)
        return httpx.Response(201, json={"receipts": [{"id": "rcpt_1"}, {"id": "rcpt_2"}]})

    inv = _inv_with_handler(handler)
    out = inv.receipts.create_batch(
        [
            {"source": "stripe", "kind": "refund"},
            {"source": "zendesk", "kind": "ticket"},
        ]
    )
    assert seen["path"] == "/v1/receipts/batch"
    assert seen["body"] == {
        "receipts": [
            {"source": "stripe", "kind": "refund"},
            {"source": "zendesk", "kind": "ticket"},
        ]
    }
    assert out == [{"id": "rcpt_1"}, {"id": "rcpt_2"}]


def test_receipts_list_passes_filters():
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["query"] = dict(request.url.params)
        return httpx.Response(200, json={"data": [], "next_cursor": None})

    inv = _inv_with_handler(handler)
    inv.receipts.list(run_id="run_1", source="stripe", kind="refund", limit=5)
    assert seen["path"] == "/v1/receipts"
    assert seen["query"] == {
        "run_id": "run_1",
        "source": "stripe",
        "kind": "refund",
        "limit": "5",
    }


def test_receipts_get_unwraps():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/receipts/rcpt_1"
        return httpx.Response(200, json={"receipt": {"id": "rcpt_1"}})

    inv = _inv_with_handler(handler)
    assert inv.receipts.get("rcpt_1") == {"id": "rcpt_1"}
