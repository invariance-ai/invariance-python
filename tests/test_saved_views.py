"""Tests for SavedViewsResource (sync)."""

from __future__ import annotations

import json

import httpx
import pytest

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


def test_saved_views_list_no_cursor_envelope():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/v1/saved-views"
        return httpx.Response(200, json={"data": [{"id": "sv_1"}]})

    inv = _inv_with_handler(handler)
    out = inv.saved_views.list()
    assert out == {"data": [{"id": "sv_1"}]}


def test_saved_views_create_unwraps_view():
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["path"] = request.url.path
        seen["body"] = json.loads(request.content)
        return httpx.Response(201, json={"view": {"id": "sv_1", "name": "Refunds"}})

    inv = _inv_with_handler(handler)
    out = inv.saved_views.create(
        name="Refunds",
        source="runs",
        spec={"aggregation": "count"},
        viz="metric",
        visibility="agent",
    )
    assert seen["method"] == "POST"
    assert seen["path"] == "/v1/saved-views"
    assert seen["body"] == {
        "name": "Refunds",
        "source": "runs",
        "spec": {"aggregation": "count"},
        "viz": "metric",
        "visibility": "agent",
    }
    assert out == {"id": "sv_1", "name": "Refunds"}


def test_saved_views_get_and_update_and_delete():
    calls: list = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, request.url.path))
        if request.method == "DELETE":
            return httpx.Response(200, json={"ok": True})
        return httpx.Response(200, json={"view": {"id": "sv_1", "name": "X"}})

    inv = _inv_with_handler(handler)
    assert inv.saved_views.get("sv_1") == {"id": "sv_1", "name": "X"}
    assert inv.saved_views.update("sv_1", name="X") == {"id": "sv_1", "name": "X"}
    assert inv.saved_views.delete("sv_1") is None
    assert calls == [
        ("GET", "/v1/saved-views/sv_1"),
        ("PATCH", "/v1/saved-views/sv_1"),
        ("DELETE", "/v1/saved-views/sv_1"),
    ]


def test_saved_views_run_by_id():
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"result": {"source": "runs", "row_count": 0}})

    inv = _inv_with_handler(handler)
    out = inv.saved_views.run(saved_view_id="sv_1")
    assert seen["path"] == "/v1/saved-views/run"
    assert seen["body"] == {"saved_view_id": "sv_1"}
    assert out == {"source": "runs", "row_count": 0}


def test_saved_views_run_inline_source_spec():
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"result": {"source": "events", "row_count": 3}})

    inv = _inv_with_handler(handler)
    out = inv.saved_views.run(source="events", spec={"limit": 5})
    assert seen["body"] == {"source": "events", "spec": {"limit": 5}}
    assert out["row_count"] == 3


def test_saved_views_run_validates_exactly_one():
    inv = _inv_with_handler(lambda r: httpx.Response(200, json={}))
    with pytest.raises(ValueError):
        inv.saved_views.run()
    with pytest.raises(ValueError):
        inv.saved_views.run(saved_view_id="sv_1", source="runs")
