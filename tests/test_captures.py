"""Tests for CapturesResource."""

from __future__ import annotations

import json

import httpx
import pytest

from invariance import Invariance, CapturesResource


def _inv_with_handler(handler):
    transport = httpx.MockTransport(handler)
    inv = Invariance(api_key="inv_test", api_url="http://test.local")
    inv._http._client = httpx.Client(
        base_url="http://test.local",
        headers={"Authorization": "Bearer inv_test"},
        transport=transport,
    )
    return inv


def _session(**kwargs):
    base = {"id": "cap_1", "source": "claude-code", "run_id": None}
    base.update(kwargs)
    return base


# ── Registration ───────────────────────────────────────────────────────────


def test_captures_registered_on_client():
    inv = Invariance(api_key="inv_test", api_url="http://test.local")
    assert isinstance(inv.captures, CapturesResource)


# ── create ─────────────────────────────────────────────────────────────────


def test_create_posts_to_v1_captures():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["path"] = request.url.path
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"session": _session()})

    inv = _inv_with_handler(handler)
    result = inv.captures.create(source="claude-code")
    assert seen["method"] == "POST"
    assert seen["path"] == "/v1/captures"
    assert seen["body"] == {"source": "claude-code"}
    assert result["id"] == "cap_1"


def test_create_strips_unset_optional_fields():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"session": _session()})

    inv = _inv_with_handler(handler)
    inv.captures.create(source="claude-code")
    # Only "source" should be in the body — no None-valued keys
    assert list(seen["body"].keys()) == ["source"]


def test_create_includes_optional_fields_when_provided():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"session": _session(run_id="run_1")})

    inv = _inv_with_handler(handler)
    inv.captures.create(
        source="claude-code",
        session_type="chat",
        title="My session",
        run_id="run_1",
        metadata={"k": "v"},
    )
    assert seen["body"]["source"] == "claude-code"
    assert seen["body"]["session_type"] == "chat"
    assert seen["body"]["title"] == "My session"
    assert seen["body"]["run_id"] == "run_1"
    assert seen["body"]["metadata"] == {"k": "v"}


def test_create_forwards_tags():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"session": _session()})

    inv = _inv_with_handler(handler)
    inv.captures.create(source="claude-code", tags=["meeting", "q3"])
    assert seen["body"]["tags"] == ["meeting", "q3"]


# ── get ────────────────────────────────────────────────────────────────────


def test_get_hits_correct_path():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["path"] = request.url.path
        return httpx.Response(200, json={"session": _session()})

    inv = _inv_with_handler(handler)
    result = inv.captures.get("cap_1")
    assert seen["method"] == "GET"
    assert seen["path"] == "/v1/captures/cap_1"
    assert result["id"] == "cap_1"


# ── list ───────────────────────────────────────────────────────────────────


def test_list_no_params():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["params"] = dict(request.url.params)
        return httpx.Response(200, json={"data": [], "next_cursor": None})

    inv = _inv_with_handler(handler)
    inv.captures.list()
    assert seen["path"] == "/v1/captures"
    assert seen["params"] == {}


def test_list_forwards_run_id_and_limit():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["params"] = dict(request.url.params)
        return httpx.Response(200, json={"data": [], "next_cursor": None})

    inv = _inv_with_handler(handler)
    inv.captures.list(run_id="run_42", limit=10, cursor="c_1")
    assert seen["params"]["run_id"] == "run_42"
    assert seen["params"]["limit"] == "10"
    assert seen["params"]["cursor"] == "c_1"


def test_list_forwards_filter_params():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["params"] = dict(request.url.params)
        return httpx.Response(200, json={"data": [], "next_cursor": None})

    inv = _inv_with_handler(handler)
    inv.captures.list(project_id="proj_1", operator_id="op_1", source="claude-code")
    assert seen["params"]["project_id"] == "proj_1"
    assert seen["params"]["operator_id"] == "op_1"
    assert seen["params"]["source"] == "claude-code"


def test_list_forwards_tags_filter():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["params"] = dict(request.url.params)
        return httpx.Response(200, json={"data": [], "next_cursor": None})

    inv = _inv_with_handler(handler)
    inv.captures.list(tags="meeting,q3")
    assert seen["params"]["tags"] == "meeting,q3"


# ── link ───────────────────────────────────────────────────────────────────


def test_link_patches_run_id():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["path"] = request.url.path
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"session": _session(run_id="run_99")})

    inv = _inv_with_handler(handler)
    result = inv.captures.link("cap_1", run_id="run_99")
    assert seen["method"] == "PATCH"
    assert seen["path"] == "/v1/captures/cap_1"
    assert seen["body"] == {"run_id": "run_99"}
    assert result["run_id"] == "run_99"


# ── unlink ─────────────────────────────────────────────────────────────────


def test_unlink_patches_run_id_null():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["path"] = request.url.path
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"session": _session(run_id=None)})

    inv = _inv_with_handler(handler)
    result = inv.captures.unlink("cap_1")
    assert seen["method"] == "PATCH"
    assert seen["path"] == "/v1/captures/cap_1"
    assert seen["body"] == {"run_id": None}
    assert result["run_id"] is None


# ── update ─────────────────────────────────────────────────────────────────


def test_update_status_only():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"session": _session(status="completed")})

    inv = _inv_with_handler(handler)
    inv.captures.update("cap_1", status="completed")
    assert seen["body"] == {"status": "completed"}


def test_update_run_id_none_sends_null():
    """Passing run_id=None explicitly to update() should send {run_id: null}."""
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"session": _session()})

    inv = _inv_with_handler(handler)
    inv.captures.update("cap_1", run_id=None)
    assert "run_id" in seen["body"]
    assert seen["body"]["run_id"] is None


def test_update_omits_unset_run_id():
    """Not passing run_id at all should not include it in the body."""
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"session": _session()})

    inv = _inv_with_handler(handler)
    inv.captures.update("cap_1", status="completed")
    assert "run_id" not in seen["body"]


def test_update_forwards_tags():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"session": _session()})

    inv = _inv_with_handler(handler)
    inv.captures.update("cap_1", tags=["done"])
    assert seen["body"]["tags"] == ["done"]


# ── list_links ─────────────────────────────────────────────────────────────


def test_list_links_returns_run_id():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"session": _session(run_id="run_77")})

    inv = _inv_with_handler(handler)
    result = inv.captures.list_links("cap_1")
    assert result == {"run_id": "run_77"}


def test_list_links_returns_none_when_unlinked():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"session": _session(run_id=None)})

    inv = _inv_with_handler(handler)
    result = inv.captures.list_links("cap_1")
    assert result == {"run_id": None}
