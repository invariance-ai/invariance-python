"""Tests for NarrativesResource (sync + async)."""

import asyncio

import httpx
import pytest

from invariance import AsyncInvariance, Invariance

_NARRATIVE_FIXTURE = {
    "run_id": "run_1",
    "agent_id": "agent_1",
    "narrative": "Summary text.",
    "key_moments": ["moment one"],
    "root_cause": "unit-test",
    "scorer": "severity",
    "model": "claude-sonnet-4-20250514",
    "provider": "anthropic",
    "scored_node_count": 3,
    "total_node_count": 10,
    "created_at": "2026-04-19T00:00:00Z",
    "updated_at": "2026-04-19T00:00:00Z",
}


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


def test_narratives_get_hits_expected_path():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["path"] = request.url.path
        seen["query"] = request.url.query.decode()
        return httpx.Response(200, json={"narrative": _NARRATIVE_FIXTURE})

    inv = _inv_with_handler(handler)
    n = inv.narratives.get("run_1")
    assert seen["method"] == "GET"
    assert seen["path"] == "/v1/runs/run_1/narrative"
    assert seen["query"] == ""
    assert n["provider"] == "anthropic"
    assert n["scorer"] == "severity"


def test_narratives_get_refresh_true_passes_query():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["query"] = request.url.query.decode()
        return httpx.Response(200, json={"narrative": _NARRATIVE_FIXTURE})

    inv = _inv_with_handler(handler)
    inv.narratives.get("run_1", refresh=True)
    assert seen["query"] == "refresh=true"


def test_narratives_get_surfaces_503_as_api_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            503,
            json={"error": {"code": "internal_error", "message": "No LLM provider configured"}},
        )

    inv = _inv_with_handler(handler)
    from invariance import InvarianceApiError

    with pytest.raises(InvarianceApiError) as exc:
        inv.narratives.get("run_1")
    assert exc.value.status == 503


def test_async_narratives_get_hits_expected_path():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["path"] = request.url.path
        seen["query"] = request.url.query.decode()
        return httpx.Response(200, json={"narrative": _NARRATIVE_FIXTURE})

    async def run() -> dict:
        inv = _async_inv_with_handler(handler)
        try:
            return await inv.narratives.get("run_1", refresh=True)
        finally:
            await inv.aclose()

    n = asyncio.run(run())
    assert seen["method"] == "GET"
    assert seen["path"] == "/v1/runs/run_1/narrative"
    assert seen["query"] == "refresh=true"
    assert n["run_id"] == "run_1"


def test_async_narratives_get_surfaces_503_as_api_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            503,
            json={"error": {"code": "internal_error", "message": "No LLM provider configured"}},
        )

    async def run() -> None:
        inv = _async_inv_with_handler(handler)
        from invariance import InvarianceApiError

        try:
            with pytest.raises(InvarianceApiError) as exc:
                await inv.narratives.get("run_1")
            assert exc.value.status == 503
        finally:
            await inv.aclose()

    asyncio.run(run())
