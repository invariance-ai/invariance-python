"""Tests for the Step context manager, buffered writes, and @trace."""

import json

import httpx
import pytest

from invariance import Invariance, trace


def _inv_with_capture():
    """Return (inv, calls) where calls accumulates every POST request body."""
    calls: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        body = request.content.decode() if request.content else ""
        parsed = json.loads(body) if body else None
        calls.append({"method": request.method, "path": path, "body": parsed})

        if request.method == "POST" and path == "/v1/runs":
            return httpx.Response(
                200,
                json={"run": {"id": "run_1", "agent_id": "a_1", "name": "t", "status": "open"}},
            )
        if request.method == "POST" and path == "/v1/nodes":
            items = parsed if isinstance(parsed, list) else [parsed]
            data = [{**item, "hash": f"h_{i}"} for i, item in enumerate(items)]
            return httpx.Response(200, json={"data": data})
        if request.method == "PATCH" and path.startswith("/v1/runs/"):
            return httpx.Response(
                200,
                json={"run": {"id": "run_1", "agent_id": "a_1", "name": "t", "status": "completed"}},
            )
        return httpx.Response(404, json={"error": {"code": "nf", "message": "nf"}})

    transport = httpx.MockTransport(handler)
    inv = Invariance(api_key="inv_test_abc", api_url="http://test.local")
    inv._http._client = httpx.Client(
        base_url="http://test.local",
        headers={"Authorization": "Bearer inv_test_abc"},
        transport=transport,
    )
    return inv, calls


def test_run_as_context_manager_finishes():
    inv, calls = _inv_with_capture()
    with inv.runs.start(name="demo") as run:
        assert run.run_id == "run_1"

    # Last call should be a PATCH setting status=completed.
    patches = [c for c in calls if c["method"] == "PATCH"]
    assert len(patches) == 1
    assert patches[0]["body"]["status"] == "completed"


def test_step_emits_node_with_captured_fields():
    inv, calls = _inv_with_capture()
    with inv.runs.start() as run:
        with run.step("tool_call", input={"q": 1}) as s:
            s.output = {"answer": "ok"}

    posts = [c for c in calls if c["method"] == "POST" and c["path"] == "/v1/nodes"]
    assert len(posts) == 1
    # Buffered flow sends a batch (list body).
    nodes = posts[0]["body"] if isinstance(posts[0]["body"], list) else [posts[0]["body"]]
    assert len(nodes) == 1
    n = nodes[0]
    assert n["run_id"] == "run_1"
    assert n["action_type"] == "tool_call"
    assert n["input"] == {"q": 1}
    assert n["output"] == {"answer": "ok"}
    assert "duration_ms" in n


def test_nested_steps_link_via_parent_id():
    inv, calls = _inv_with_capture()
    outer_id = None
    inner_id = None
    with inv.runs.start() as run:
        with run.step("outer") as outer:
            outer_id = outer.id
            with run.step("inner") as inner:
                inner_id = inner.id

    posts = [c for c in calls if c["path"] == "/v1/nodes"]
    # Both nodes flushed in one batch on run exit.
    nodes = posts[0]["body"]
    by_id = {n["id"]: n for n in nodes}
    assert by_id[outer_id].get("parent_id") is None
    assert by_id[inner_id]["parent_id"] == outer_id


def test_step_captures_exception_into_error():
    inv, calls = _inv_with_capture()
    with pytest.raises(ValueError):
        with inv.runs.start() as run:
            with run.step("boom"):
                raise ValueError("nope")

    # Step emits a node carrying error; run is failed.
    posts = [c for c in calls if c["path"] == "/v1/nodes"]
    nodes = posts[0]["body"] if isinstance(posts[0]["body"], list) else [posts[0]["body"]]
    assert nodes[0]["error"]["type"] == "ValueError"
    assert nodes[0]["error"]["message"] == "nope"

    patches = [c for c in calls if c["method"] == "PATCH"]
    assert patches[0]["body"]["status"] == "failed"


def test_unbuffered_mode_posts_per_step():
    inv, calls = _inv_with_capture()
    with inv.runs.start(buffered=False) as run:
        with run.step("a"):
            pass
        with run.step("b"):
            pass

    posts = [c for c in calls if c["path"] == "/v1/nodes"]
    # Two individual POSTs, each with a single-node body.
    assert len(posts) == 2


def test_trace_decorator_captures_args_and_return():
    inv, calls = _inv_with_capture()
    with inv.runs.start() as run:

        @trace(run, action_type="lookup")
        def lookup(x: int, y: int = 2) -> int:
            return x + y

        assert lookup(3, y=4) == 7

    posts = [c for c in calls if c["path"] == "/v1/nodes"]
    nodes = posts[0]["body"] if isinstance(posts[0]["body"], list) else [posts[0]["body"]]
    assert nodes[0]["action_type"] == "lookup"
    assert nodes[0]["input"] == {"x": 3, "y": 4}
    assert nodes[0]["output"] == 7
