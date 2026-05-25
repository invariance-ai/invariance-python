"""Tests for MetricsResource (sync)."""

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


def test_metrics_overview_default_window():
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["query"] = dict(request.url.params)
        return httpx.Response(200, json={"metrics": {"window_hours": 24, "success_rate": 1.0}})

    inv = _inv_with_handler(handler)
    out = inv.metrics.overview()
    assert seen["path"] == "/v1/metrics/overview"
    assert seen["query"] == {}
    assert out == {"window_hours": 24, "success_rate": 1.0}


def test_metrics_overview_window_hours():
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["query"] = dict(request.url.params)
        return httpx.Response(200, json={"metrics": {"window_hours": 168}})

    inv = _inv_with_handler(handler)
    inv.metrics.overview(window_hours=168)
    assert seen["query"] == {"window_hours": "168"}


def test_metrics_agents_unwraps_usage():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/metrics/agents"
        return httpx.Response(200, json={"usage": [{"agent_id": "a_1", "run_count": 5}]})

    inv = _inv_with_handler(handler)
    out = inv.metrics.agents(window_hours=24)
    assert out == [{"agent_id": "a_1", "run_count": 5}]
