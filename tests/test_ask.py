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


def _ask_response() -> dict:
    return {
        "session": {
            "id": "kbs_1",
            "agent_id": "a",
            "project_id": "p",
            "title": "t",
            "model": None,
            "created_at": "",
            "updated_at": "",
        },
        "messages": [],
        "final_text": "hello",
        "turns": 1,
    }


def test_send_posts_message_and_max_turns():
    captured: list[bytes] = []

    def handler(req: httpx.Request) -> httpx.Response:
        captured.append(req.content)
        assert req.method == "POST"
        assert req.url.path == "/v1/ask"
        return httpx.Response(200, json=_ask_response())

    inv = _client_with_handler(handler)
    out = inv.ask.send("hi", max_turns=4)
    body = json.loads(captured[0])
    assert body == {"message": "hi", "max_turns": 4}
    assert out["final_text"] == "hello"
    assert out["turns"] == 1


def test_send_passes_session_id_for_resume():
    captured: list[bytes] = []

    def handler(req: httpx.Request) -> httpx.Response:
        captured.append(req.content)
        return httpx.Response(200, json=_ask_response())

    inv = _client_with_handler(handler)
    inv.ask.send("follow up", session_id="kbs_1")
    body = json.loads(captured[0])
    assert body["session_id"] == "kbs_1"
