"""Tests for MemoryResource and AsyncMemoryResource."""

from __future__ import annotations

import json

import httpx
import pytest

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


_ACCESS = {
    "id": "ma_1",
    "run_id": "run_1",
    "node_id": "node_1",
    "agent_id": "agent_1",
    "access_type": "read",
    "subject_type": "customer",
    "subject_id": "c_42",
    "key": "preferred_channel",
    "value": None,
    "used_for": "ticket-triage",
    "source_node_id": None,
    "timestamp": "2026-05-08T00:00:00Z",
}


def test_memory_read_posts_expected_body():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["path"] = request.url.path
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"access": _ACCESS, "record": None})

    inv = _inv_with_handler(handler)
    res = inv.memory.read(
        subject_type="customer",
        subject_id="c_42",
        key="preferred_channel",
        used_for="ticket-triage",
        run_id="run_1",
        node_id="node_1",
    )
    assert seen["method"] == "POST"
    assert seen["path"] == "/v1/memory/read"
    assert seen["body"] == {
        "subject_type": "customer",
        "subject_id": "c_42",
        "key": "preferred_channel",
        "used_for": "ticket-triage",
        "run_id": "run_1",
        "node_id": "node_1",
    }
    assert res["record"] is None


def test_memory_read_falls_back_to_env_ids(monkeypatch):
    monkeypatch.setenv("INVARIANCE_RUN_ID", "run_env")
    monkeypatch.setenv("INVARIANCE_NODE_ID", "node_env")
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"access": _ACCESS, "record": None})

    inv = _inv_with_handler(handler)
    inv.memory.read(
        subject_type="customer",
        subject_id="c_42",
        key="k",
        used_for="why",
    )
    assert seen["body"]["run_id"] == "run_env"
    assert seen["body"]["node_id"] == "node_env"


def test_memory_write_defaults_source_and_confidence():
    seen = {}
    record = {
        "id": "mr_1",
        "agent_id": "agent_1",
        "subject_type": "customer",
        "subject_id": "c_42",
        "claim": "preferred_channel=email",
        "value": "email",
        "source": "agent_write",
        "confidence": 1.0,
        "valid_from": "2026-05-08T00:00:00Z",
        "valid_until": None,
        "last_verified_at": None,
        "superseded_by": None,
        "provenance": [],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["body"] = json.loads(request.content)
        access = {**_ACCESS, "access_type": "write", "value": "email"}
        return httpx.Response(200, json={"access": access, "record": record})

    inv = _inv_with_handler(handler)
    res = inv.memory.write(
        subject_type="customer",
        subject_id="c_42",
        key="preferred_channel",
        value="email",
        used_for="ticket-triage",
    )
    assert seen["path"] == "/v1/memory/write"
    assert seen["body"]["source"] == "agent_write"
    assert seen["body"]["confidence"] == 1.0
    assert seen["body"]["value"] == "email"
    assert "provenance" not in seen["body"]
    assert "valid_until" not in seen["body"]
    assert res["record"]["id"] == "mr_1"


def test_memory_write_passes_optional_fields():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"access": _ACCESS, "record": {}})

    inv = _inv_with_handler(handler)
    inv.memory.write(
        subject_type="policy",
        subject_id="pol_1",
        key="kyc",
        value={"tier": "B"},
        used_for="risk-assessment",
        source="policy_doc",
        confidence=0.85,
        provenance=[{"kind": "document", "id": "doc_1"}],
        valid_until="2026-12-31T23:59:59Z",
    )
    assert seen["body"]["source"] == "policy_doc"
    assert seen["body"]["confidence"] == 0.85
    assert seen["body"]["provenance"] == [{"kind": "document", "id": "doc_1"}]
    assert seen["body"]["valid_until"] == "2026-12-31T23:59:59Z"


@pytest.mark.asyncio
async def test_async_memory_read_posts_expected_body():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["path"] = request.url.path
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"access": _ACCESS, "record": None})

    inv = _async_inv_with_handler(handler)
    try:
        res = await inv.memory.read(
            subject_type="customer",
            subject_id="c_42",
            key="preferred_channel",
            used_for="async-test",
            run_id="run_1",
            node_id="node_1",
        )
        assert seen["method"] == "POST"
        assert seen["path"] == "/v1/memory/read"
        assert seen["body"]["used_for"] == "async-test"
        assert res["record"] is None
    finally:
        await inv.aclose()


@pytest.mark.asyncio
async def test_async_memory_write_defaults():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"access": _ACCESS, "record": {}})

    inv = _async_inv_with_handler(handler)
    try:
        await inv.memory.write(
            subject_type="user",
            subject_id="u_1",
            key="locale",
            value="en-US",
            used_for="personalization",
        )
        assert seen["body"]["source"] == "agent_write"
        assert seen["body"]["confidence"] == 1.0
    finally:
        await inv.aclose()
