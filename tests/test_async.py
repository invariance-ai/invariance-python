"""Tests for AsyncInvariance, AsyncRun, AsyncStep, async_trace."""

import asyncio
import json

import httpx
import pytest

from invariance import AsyncInvariance, async_trace


def _async_inv_with_capture():
    calls: list[dict] = []

    async def handler(request: httpx.Request) -> httpx.Response:
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
    inv = AsyncInvariance(api_key="inv_test_abc", api_url="http://test.local")
    # Replace the internal async client with our transport-mocked one.
    inv._http._client = httpx.AsyncClient(
        base_url="http://test.local",
        headers={"Authorization": "Bearer inv_test_abc"},
        transport=transport,
    )
    return inv, calls


@pytest.mark.asyncio
async def test_async_run_step_and_finish():
    inv, calls = _async_inv_with_capture()
    async with inv:
        async with await inv.runs.start(name="demo") as run:
            async with run.step("plan", input={"g": "x"}) as s:
                s.output = {"plan": [1, 2]}

    posts = [c for c in calls if c["path"] == "/v1/nodes"]
    assert len(posts) == 1
    nodes = posts[0]["body"]
    assert nodes[0]["action_type"] == "plan"
    assert nodes[0]["output"] == {"plan": [1, 2]}

    patches = [c for c in calls if c["method"] == "PATCH"]
    assert patches[0]["body"]["status"] == "completed"


@pytest.mark.asyncio
async def test_async_nested_parent_id():
    inv, calls = _async_inv_with_capture()
    outer_id = None
    inner_id = None
    async with inv:
        async with await inv.runs.start() as run:
            async with run.step("outer") as outer:
                outer_id = outer.id
                async with run.step("inner") as inner:
                    inner_id = inner.id

    nodes = [c for c in calls if c["path"] == "/v1/nodes"][0]["body"]
    by_id = {n["id"]: n for n in nodes}
    assert by_id[outer_id].get("parent_id") is None
    assert by_id[inner_id]["parent_id"] == outer_id


@pytest.mark.asyncio
async def test_async_concurrent_steps_serialize():
    """Two concurrent tasks writing steps to the same run must not race.

    The backend cannot detect branched chains; the SDK's per-run
    :class:`asyncio.Lock` is what prevents two concurrent ``_emit`` calls
    from producing interleaved writes. We verify both nodes land and the
    run still finishes cleanly.
    """
    inv, calls = _async_inv_with_capture()
    async with inv:
        async with await inv.runs.start() as run:

            async def work(label: str) -> None:
                async with run.step(label):
                    await asyncio.sleep(0)  # yield to other task

            await asyncio.gather(work("a"), work("b"))

    nodes = [c for c in calls if c["path"] == "/v1/nodes"][0]["body"]
    labels = sorted(n["action_type"] for n in nodes)
    assert labels == ["a", "b"]


@pytest.mark.asyncio
async def test_async_trace_decorator():
    inv, calls = _async_inv_with_capture()
    async with inv:
        async with await inv.runs.start() as run:

            @async_trace(run, action_type="fetch")
            async def fetch(x: int) -> int:
                return x * 2

            assert (await fetch(7)) == 14

    nodes = [c for c in calls if c["path"] == "/v1/nodes"][0]["body"]
    assert nodes[0]["action_type"] == "fetch"
    assert nodes[0]["input"] == {"x": 7}
    assert nodes[0]["output"] == 14


@pytest.mark.asyncio
async def test_async_monitors_delete_sends_delete_and_handles_204():
    seen: dict = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["path"] = request.url.path
        return httpx.Response(204)

    transport = httpx.MockTransport(handler)
    inv = AsyncInvariance(api_key="inv_test", api_url="http://test.local")
    inv._http._client = httpx.AsyncClient(
        base_url="http://test.local",
        headers={"Authorization": "Bearer inv_test"},
        transport=transport,
    )
    async with inv:
        result = await inv.monitors.delete("mon_42")
    assert result is None
    assert seen == {"method": "DELETE", "path": "/v1/monitors/mon_42"}


@pytest.mark.asyncio
async def test_async_handoff_fields_emit():
    inv, calls = _async_inv_with_capture()
    async with inv:
        async with await inv.runs.start() as run:
            async with run.step(
                "delegate",
                handoff_from="a_1",
                handoff_to="a_2",
                handoff_reason="needs research",
            ):
                pass
            token = await run.handoff("a_3", reason="hand over", message={"ctx": 1})

    nodes = [c for c in calls if c["path"] == "/v1/nodes"][0]["body"]
    assert nodes[0]["handoff_to"] == "a_2"
    assert nodes[0]["handoff_from"] == "a_1"
    assert nodes[0]["handoff_reason"] == "needs research"
    assert nodes[1]["action_type"] == "handoff"
    assert nodes[1]["handoff_to"] == "a_3"
    assert nodes[1]["handoff_reason"] == "hand over"
    assert token is None


def _async_inv_with_handler(handler):
    transport = httpx.MockTransport(handler)
    inv = AsyncInvariance(api_key="inv_test", api_url="http://test.local")
    inv._http._client = httpx.AsyncClient(
        base_url="http://test.local",
        headers={"Authorization": "Bearer inv_test"},
        transport=transport,
    )
    return inv


@pytest.mark.asyncio
async def test_async_memory_read_and_write():
    seen: list[dict] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        seen.append({"method": request.method, "path": request.url.path, "body": json.loads(request.content)})
        return httpx.Response(
            200,
            json={
                "access": {
                    "id": "ma_1",
                    "run_id": "r_1",
                    "node_id": "n_1",
                    "agent_id": "a_1",
                    "access_type": "read",
                    "subject_type": "customer",
                    "subject_id": "cust_1",
                    "key": "plan",
                    "value": None,
                    "used_for": "x",
                    "source_node_id": None,
                    "timestamp": "t",
                },
                "record": None,
            },
        )

    inv = _async_inv_with_handler(handler)
    async with inv:
        await inv.memory.read(subject_type="customer", subject_id="cust_1", key="plan", used_for="x", run_id="r_1")
        await inv.memory.write(subject_type="customer", subject_id="cust_1", key="plan", value="pro", used_for="x", run_id="r_1")
    assert seen[0]["path"] == "/v1/memory/read"
    assert seen[1]["path"] == "/v1/memory/write"
    assert seen[1]["body"]["source"] == "agent_write"
    assert seen[1]["body"]["value"] == "pro"


@pytest.mark.asyncio
async def test_async_evals_run_case_passes():
    async def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        method = request.method
        if method == "POST" and path == "/v1/runs":
            return httpx.Response(200, json={"run": {"id": "run_eval", "agent_id": "a", "name": "x", "status": "open", "metadata": json.loads(request.content).get("metadata", {}), "created_at": "t", "updated_at": "t"}})
        if method == "PATCH":
            return httpx.Response(200, json={"run": {"id": "run_eval", "status": "completed"}})
        if method == "GET" and path == "/v1/findings":
            return httpx.Response(200, json={"data": [], "next_cursor": None})
        return httpx.Response(404)

    inv = _async_inv_with_handler(handler)
    async with inv:
        async def h(run):
            return None
        result = await inv.evals.run_case(suite="s", case="c", handler=h)
    assert result["status"] == "pass"
    assert result["run_id"] == "run_eval"


@pytest.mark.asyncio
async def test_async_operators_me_hits_path():
    seen: dict = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        return httpx.Response(200, json={"operator": {"id": "op_1", "name": "n"}})

    inv = _async_inv_with_handler(handler)
    async with inv:
        res = await inv.operators.me()
    assert seen["path"] == "/v1/operators/me"
    assert res["operator"]["id"] == "op_1"


@pytest.mark.asyncio
async def test_async_sessions_from_claude_code_defaults():
    seen: dict = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"session": {"id": "sess_1"}})

    inv = _async_inv_with_handler(handler)
    async with inv:
        await inv.sessions.from_claude_code(title="my run")
    assert seen["body"]["source"] == "claude_code"
    assert seen["body"]["session_type"] == "coding"
    assert seen["body"]["title"] == "my run"


@pytest.mark.asyncio
async def test_async_runs_operational_graph_hits_expected_path():
    seen: dict = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["path"] = request.url.path
        return httpx.Response(
            200,
            json={
                "run_id": "run_1",
                "entities": [],
                "edges": [],
                "findings": [],
                "completeness": {
                    "business_object_linked": True,
                    "policy_context_found": False,
                    "owner_found": False,
                    "approval_context_found": False,
                    "downstream_state_change_found": False,
                    "score": 0.2,
                },
            },
        )

    inv = _async_inv_with_handler(handler)
    async with inv:
        graph = await inv.runs.operational_graph("run_1")
    assert seen["method"] == "GET"
    assert seen["path"] == "/v1/runs/run_1/operational-graph"
    assert graph["completeness"]["score"] == 0.2


# ── Data-plane parity: new async resources ──────────────────────────────────


@pytest.mark.asyncio
async def test_async_divergences_list_get_update():
    calls: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else None
        calls.append({"method": request.method, "path": request.url.path,
                      "query": dict(request.url.params), "body": body})
        if request.method == "PATCH":
            return httpx.Response(200, json={"divergence": {"id": "dv_1", "status": "accepted"}})
        if request.url.path == "/v1/divergences/dv_1":
            return httpx.Response(200, json={"divergence": {"id": "dv_1"}})
        return httpx.Response(200, json={"data": [], "next_cursor": None})

    inv = _async_inv_with_handler(handler)
    async with inv:
        await inv.divergences.list(kind="policy", status="open")
        got = await inv.divergences.get("dv_1")
        upd = await inv.divergences.update("dv_1", status="accepted")
    assert got == {"id": "dv_1"}
    assert upd["status"] == "accepted"
    assert calls[0]["query"] == {"kind": "policy", "status": "open"}
    assert calls[2]["body"] == {"status": "accepted"}


@pytest.mark.asyncio
async def test_async_saved_views_run_and_validation():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"result": {"source": "runs", "row_count": 0}})

    inv = _async_inv_with_handler(handler)
    async with inv:
        out = await inv.saved_views.run(saved_view_id="sv_1")
        assert out["row_count"] == 0
        with pytest.raises(ValueError):
            await inv.saved_views.run()
        with pytest.raises(ValueError):
            await inv.saved_views.run(saved_view_id="sv_1", source="runs")


@pytest.mark.asyncio
async def test_async_receipts_create_and_batch():
    calls: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else None
        calls.append({"path": request.url.path, "body": body})
        if request.url.path == "/v1/receipts/batch":
            return httpx.Response(201, json={"receipts": [{"id": "r_1"}]})
        return httpx.Response(201, json={"receipt": {"id": "r_1"}})

    inv = _async_inv_with_handler(handler)
    async with inv:
        created = await inv.receipts.create(source="stripe", kind="refund")
        batched = await inv.receipts.create_batch([{"source": "slack", "kind": "msg"}])
    assert created == {"id": "r_1"}
    assert batched == [{"id": "r_1"}]
    assert calls[0]["body"] == {"source": "stripe", "kind": "refund"}
    assert calls[1]["path"] == "/v1/receipts/batch"


@pytest.mark.asyncio
async def test_async_workflow_observability():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/executions"):
            return httpx.Response(200, json={"data": [{"case_id": "c_1"}], "next_cursor": None})
        if request.url.path == "/v1/workflow-observability/wf.a":
            return httpx.Response(200, json={"rollup": {"workflow_key": "wf.a"}})
        return httpx.Response(200, json={"data": [], "next_cursor": None})

    inv = _async_inv_with_handler(handler)
    async with inv:
        assert (await inv.workflow_observability.list())["data"] == []
        assert (await inv.workflow_observability.get("wf.a"))["workflow_key"] == "wf.a"
        ex = await inv.workflow_observability.executions("wf.a")
    assert ex["data"] == [{"case_id": "c_1"}]


@pytest.mark.asyncio
async def test_async_metrics_overview_and_agents():
    calls: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append({"path": request.url.path, "query": dict(request.url.params)})
        if request.url.path == "/v1/metrics/agents":
            return httpx.Response(200, json={"usage": [{"agent_id": "a_1"}]})
        return httpx.Response(200, json={"metrics": {"window_hours": 24}})

    inv = _async_inv_with_handler(handler)
    async with inv:
        ov = await inv.metrics.overview(window_hours=48)
        usage = await inv.metrics.agents()
    assert ov == {"window_hours": 24}
    assert usage == [{"agent_id": "a_1"}]
    assert calls[0]["query"] == {"window_hours": "48"}
