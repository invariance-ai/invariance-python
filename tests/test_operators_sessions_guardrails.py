"""Tests for OperatorsResource, RecipesResource, GuardrailsResource, SessionsResource."""

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


# ── Operators ──────────────────────────────────────────────────────────────


def test_operators_me_hits_path():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        return httpx.Response(
            200,
            json={"operator": {"id": "op_1", "name": "alice", "operator_type": "human"}},
        )

    inv = _inv_with_handler(handler)
    res = inv.operators.me()
    assert seen["path"] == "/v1/operators/me"
    assert res["operator"]["operator_type"] == "human"


def test_operators_create_includes_optional_fields():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["path"] = request.url.path
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "agent": {"id": "op_1", "name": "n", "operator_type": "agent"},
                "api_key": {
                    "id": "k_1",
                    "prefix": "inv_test",
                    "label": "default",
                    "created_at": "now",
                    "key": "raw",
                },
            },
        )

    inv = _inv_with_handler(handler)
    inv.operators.create(name="n", project_id="p_1", operator_type="agent")
    assert seen["method"] == "POST"
    assert seen["path"] == "/v1/operators"
    assert seen["body"] == {"name": "n", "project_id": "p_1", "operator_type": "agent"}


def test_operators_list_passes_filters():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["params"] = dict(request.url.params)
        return httpx.Response(200, json={"data": [], "next_cursor": None})

    inv = _inv_with_handler(handler)
    inv.operators.list(project_id="p_1", operator_type="human")
    assert seen["params"] == {"project_id": "p_1", "operator_type": "human"}


def test_operators_get_unwraps_envelope():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"operator": {"id": "op_1", "name": "n"}})

    inv = _inv_with_handler(handler)
    op = inv.operators.get("op_1")
    assert op["id"] == "op_1"


# ── Recipes ────────────────────────────────────────────────────────────────


def test_recipes_list_uses_pagination():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["params"] = dict(request.url.params)
        return httpx.Response(200, json={"data": [], "next_cursor": None})

    inv = _inv_with_handler(handler)
    inv.recipes.list(cursor="c", limit=10)
    assert seen["params"] == {"cursor": "c", "limit": "10"}


def test_recipes_update_patches_partial():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200, json={"recipe": {"id": "r_1", "enabled": False, "default_mode": "shadow"}}
        )

    inv = _inv_with_handler(handler)
    inv.recipes.update("r_1", enabled=False, default_mode="shadow")
    assert seen["method"] == "PATCH"
    assert seen["body"] == {"enabled": False, "default_mode": "shadow"}


# ── Guardrails ─────────────────────────────────────────────────────────────


def test_guardrails_create_with_recipe_id():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"guardrail": {"id": "g_1", "title": "t"}})

    inv = _inv_with_handler(handler)
    g = inv.guardrails.create(title="t", recipe_id="r_1", mode="shadow")
    assert seen["body"] == {"title": "t", "recipe_id": "r_1", "mode": "shadow"}
    assert g["id"] == "g_1"


def test_guardrails_promote_posts_target_status():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"guardrail": {"id": "g_1", "status": "active_monitor"}})

    inv = _inv_with_handler(handler)
    g = inv.guardrails.promote("g_1", to="active_monitor")
    assert seen["path"] == "/v1/guardrails/g_1/promote"
    assert seen["body"] == {"to": "active_monitor"}
    assert g["status"] == "active_monitor"


def test_guardrails_list_filters():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["params"] = dict(request.url.params)
        return httpx.Response(200, json={"data": [], "next_cursor": None})

    inv = _inv_with_handler(handler)
    inv.guardrails.list(status="suggested", recipe_id="r_1")
    assert seen["params"] == {"status": "suggested", "recipe_id": "r_1"}


# ── Sessions ───────────────────────────────────────────────────────────────


def test_sessions_create_strips_unset_fields():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200, json={"session": {"id": "sess_1", "source": "claude_code"}}
        )

    inv = _inv_with_handler(handler)
    s = inv.sessions.create(source="claude_code", session_type="coding", title="T")
    assert seen["body"] == {
        "source": "claude_code",
        "session_type": "coding",
        "title": "T",
    }
    assert s["id"] == "sess_1"


def test_sessions_from_claude_code_defaults_source_and_type():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"session": {"id": "sess_1"}})

    inv = _inv_with_handler(handler)
    inv.sessions.from_claude_code(title="my run")
    assert seen["body"]["source"] == "claude_code"
    assert seen["body"]["session_type"] == "coding"
    assert seen["body"]["title"] == "my run"


def test_sessions_from_meeting_notes_defaults():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"session": {"id": "sess_2"}})

    inv = _inv_with_handler(handler)
    inv.sessions.from_meeting_notes()
    assert seen["body"] == {"source": "meeting", "session_type": "meeting"}


def test_sessions_append_events_posts_array():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"appended": 2})

    inv = _inv_with_handler(handler)
    res = inv.sessions.append_events(
        "sess_1",
        [
            {"event_type": "user_prompt", "payload": {"text": "hi"}},
            {"event_type": "assistant_message", "payload": {"text": "hello"}},
        ],
    )
    assert seen["path"] == "/v1/agent-sessions/sess_1/events"
    assert seen["body"]["events"][0]["event_type"] == "user_prompt"
    assert res["appended"] == 2


# ── Operational Context ────────────────────────────────────────────────────


def test_empty_operational_context_defaults():
    from invariance import empty_operational_context

    ctx = empty_operational_context()
    assert ctx == {
        "memory_reads": [],
        "memory_writes": [],
        "authoritative_records": [],
    }
