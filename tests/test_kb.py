import json

import httpx

from invariance import Invariance


def _client_with_handler(handler):
    transport = httpx.MockTransport(handler)
    inv = Invariance(api_key="inv_test", api_url="http://test.local")
    inv._http._client = httpx.Client(
        base_url="http://test.local",
        headers={"Authorization": "Bearer inv_test"},
        transport=transport,
    )
    return inv


# ── pages ──────────────────────────────────────────────────────────────────


def test_create_page_posts_payload_and_unwraps_page():
    seen: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        return httpx.Response(200, json={"page": {"id": "kbp_1", "path": "wiki:auth"}})

    inv = _client_with_handler(handler)
    page = inv.kb.create_page(path="wiki:auth", title="Auth", body="b")
    assert page["id"] == "kbp_1"
    assert seen[0].method == "POST"
    assert seen[0].url.path == "/v1/kb/pages"


def test_list_pages_passes_filters_and_pagination():
    captured: list[str] = []

    def handler(req: httpx.Request) -> httpx.Response:
        captured.append(str(req.url))
        return httpx.Response(200, json={"data": [], "next_cursor": None})

    inv = _client_with_handler(handler)
    inv.kb.list_pages(kind="wiki", search="auth", cursor="c_1", limit=5)
    assert "kind=wiki" in captured[0]
    assert "search=auth" in captured[0]
    assert "cursor=c_1" in captured[0]
    assert "limit=5" in captured[0]


def test_get_page():
    def handler(req: httpx.Request) -> httpx.Response:
        assert req.url.path == "/v1/kb/pages/kbp_42"
        return httpx.Response(200, json={"page": {"id": "kbp_42"}})

    inv = _client_with_handler(handler)
    assert inv.kb.get_page("kbp_42")["id"] == "kbp_42"


def test_update_page_omits_unset_fields():
    bodies: list[dict] = []

    def handler(req: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(req.content))
        return httpx.Response(200, json={"page": {"id": "kbp_1", "title": "New"}})

    inv = _client_with_handler(handler)
    inv.kb.update_page("kbp_1", title="New")
    assert bodies[0] == {"title": "New"}


def test_delete_page_handles_204():
    def handler(req: httpx.Request) -> httpx.Response:
        assert req.method == "DELETE"
        return httpx.Response(204)

    inv = _client_with_handler(handler)
    assert inv.kb.delete_page("kbp_1") is None


# ── sessions ───────────────────────────────────────────────────────────────


def test_create_session():
    def handler(req: httpx.Request) -> httpx.Response:
        assert req.url.path == "/v1/kb/sessions"
        return httpx.Response(200, json={"session": {"id": "kbs_1"}})

    inv = _client_with_handler(handler)
    assert inv.kb.create_session(title="t")["id"] == "kbs_1"


def test_list_sessions_passes_pagination():
    captured: list[str] = []

    def handler(req: httpx.Request) -> httpx.Response:
        captured.append(str(req.url))
        return httpx.Response(200, json={"data": [], "next_cursor": None})

    inv = _client_with_handler(handler)
    inv.kb.list_sessions(cursor="c_1", limit=10)
    assert "cursor=c_1" in captured[0]
    assert "limit=10" in captured[0]


def test_list_messages_unwraps_messages():
    def handler(req: httpx.Request) -> httpx.Response:
        assert req.url.path == "/v1/kb/sessions/kbs_9/messages"
        return httpx.Response(200, json={"messages": [{"id": "kbm_1"}]})

    inv = _client_with_handler(handler)
    assert inv.kb.list_messages("kbs_9") == [{"id": "kbm_1"}]


def test_append_message_posts_role_and_content():
    captured: list[bytes] = []

    def handler(req: httpx.Request) -> httpx.Response:
        captured.append(req.content)
        return httpx.Response(200, json={"message": {"id": "kbm_1"}})

    inv = _client_with_handler(handler)
    inv.kb.append_message("kbs_9", role="user", content="hi")
    body = json.loads(captured[0])
    assert body == {"content": "hi", "role": "user"}


def test_delete_session_returns_none():
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(204)

    inv = _client_with_handler(handler)
    assert inv.kb.delete_session("kbs_9") is None
