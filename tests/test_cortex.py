"""Tests for client.cortex.jobs.{create,get,result}."""

from __future__ import annotations

import json

import httpx
import pytest

from invariance import AsyncInvariance, Invariance


def _client(handler):
    transport = httpx.MockTransport(handler)
    inv = Invariance(api_key="inv_test", api_url="http://test.local")
    inv._http._client = httpx.Client(
        base_url="http://test.local",
        headers={"Authorization": "Bearer inv_test"},
        transport=transport,
    )
    return inv


def _async_client(handler):
    transport = httpx.MockTransport(handler)
    inv = AsyncInvariance(api_key="inv_test", api_url="http://test.local")
    inv._http._client = httpx.AsyncClient(
        base_url="http://test.local",
        headers={"Authorization": "Bearer inv_test"},
        transport=transport,
    )
    return inv


def test_create_posts_full_counterfactual_body():
    captured: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        captured.append(req)
        return httpx.Response(200, json={"job_id": "ctxjob_42", "status": "queued"})

    inv = _client(handler)
    out = inv.cortex.jobs.create(
        project_id="proj_123",
        job_kind="counterfactual_eval",
        target_type="case",
        target_ref="case_123",
        question="What if Alice handled the escalation earlier?",
        criteria={
            "optimize_for": ["resolution_time", "customer_satisfaction"],
            "constraints": ["do_not_expose_private_evidence"],
        },
        input_refs={"run_ids": ["run_1"], "case_ids": ["case_123"]},
        input_payload={},
        options={"use_llm": True, "create_surface_item": False},
    )
    assert captured[0].method == "POST"
    assert captured[0].url.path == "/v1/cortex/jobs"
    body = json.loads(captured[0].content)
    assert body == {
        "project_id": "proj_123",
        "job_kind": "counterfactual_eval",
        "target_type": "case",
        "target_ref": "case_123",
        "question": "What if Alice handled the escalation earlier?",
        "criteria": {
            "optimize_for": ["resolution_time", "customer_satisfaction"],
            "constraints": ["do_not_expose_private_evidence"],
        },
        "input_refs": {"run_ids": ["run_1"], "case_ids": ["case_123"]},
        "input_payload": {},
        "options": {"use_llm": True, "create_surface_item": False},
    }
    assert out["job_id"] == "ctxjob_42"
    assert out["status"] == "queued"


def test_create_omits_optional_fields_when_not_set():
    captured: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        captured.append(req)
        return httpx.Response(200, json={"job_id": "ctxjob_1", "status": "queued"})

    inv = _client(handler)
    inv.cortex.jobs.create(
        project_id="p1",
        job_kind="workflow_eval",
        target_type="run",
        target_ref="run_1",
    )
    body = json.loads(captured[0].content)
    assert set(body.keys()) == {"project_id", "job_kind", "target_type", "target_ref"}


def test_create_supports_external_target_with_payload():
    captured: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        captured.append(req)
        return httpx.Response(200, json={"job_id": "ctxjob_1", "status": "queued"})

    inv = _client(handler)
    inv.cortex.jobs.create(
        project_id="p1",
        job_kind="workflow_eval",
        target_type="external",
        target_ref="customer-sys-1",
        input_payload={"workflow_name": "refund approval", "steps": []},
    )
    body = json.loads(captured[0].content)
    assert body["target_type"] == "external"
    assert body["input_payload"] == {"workflow_name": "refund approval", "steps": []}


def test_get_uses_job_id_in_path():
    def handler(req: httpx.Request) -> httpx.Response:
        assert req.method == "GET"
        assert req.url.path == "/v1/cortex/jobs/ctxjob_abc"
        return httpx.Response(
            200,
            json={"job": {"id": "ctxjob_abc", "status": "running", "job_kind": "workflow_eval"}},
        )

    inv = _client(handler)
    out = inv.cortex.jobs.get("ctxjob_abc")
    assert out["status"] == "running"


def test_result_parses_workflow_eval():
    payload = {
        "job_id": "ctxjob_1",
        "status": "succeeded",
        "result": {
            "kind": "workflow_eval",
            "passed": True,
            "score": 0.82,
            "criteria_results": [
                {"criterion": "sla_met", "passed": True, "evidence_refs": ["case_123"]},
            ],
            "findings": [],
            "confidence": 0.8,
        },
    }

    def handler(req: httpx.Request) -> httpx.Response:
        assert req.url.path == "/v1/cortex/jobs/ctxjob_1/result"
        return httpx.Response(200, json=payload)

    inv = _client(handler)
    out = inv.cortex.jobs.result("ctxjob_1")
    assert out["status"] == "succeeded"
    assert out["result"]["kind"] == "workflow_eval"
    assert out["result"]["passed"] is True
    assert out["result"]["criteria_results"][0]["criterion"] == "sla_met"


def test_result_parses_counterfactual_with_assumptions_and_uncertainty():
    payload = {
        "job_id": "ctxjob_1",
        "status": "succeeded",
        "result": {
            "kind": "counterfactual_eval",
            "answer": "Routing to Alice likely would have reduced delay by 1-2 days.",
            "observed_outcome": "Escalation resolved after 4 days.",
            "hypothetical_change": "Alice assigned at first escalation.",
            "estimated_impact": {"resolution_time_delta": "-1.5 days"},
            "assumptions": ["Alice had bandwidth"],
            "evidence_refs": ["case_123", "run_1"],
            "confidence": 0.64,
            "uncertainty": "Low sample size: 3 similar cases.",
        },
    }

    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    inv = _client(handler)
    out = inv.cortex.jobs.result("ctxjob_1")
    r = out["result"]
    assert r["kind"] == "counterfactual_eval"
    assert r["assumptions"] == ["Alice had bandwidth"]
    assert r["uncertainty"].startswith("Low sample size")
    assert r["confidence"] == pytest.approx(0.64)


def test_result_omits_result_field_while_running():
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"job_id": "ctxjob_1", "status": "running"})

    inv = _client(handler)
    out = inv.cortex.jobs.result("ctxjob_1")
    assert out["status"] == "running"
    assert "result" not in out


@pytest.mark.asyncio
async def test_async_create_and_get():
    captured: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        captured.append(req)
        if req.method == "POST":
            return httpx.Response(200, json={"job_id": "ctxjob_9", "status": "queued"})
        return httpx.Response(
            200,
            json={"job_id": "ctxjob_9", "status": "succeeded"},
        )

    inv = _async_client(handler)
    try:
        created = await inv.cortex.jobs.create(
            project_id="p1",
            job_kind="counterfactual_eval",
            target_type="case",
            target_ref="case_1",
            question="What if?",
        )
        assert created["job_id"] == "ctxjob_9"
        got = await inv.cortex.jobs.get("ctxjob_9")
        assert got["status"] == "succeeded"
    finally:
        await inv.aclose()


COMPLEX_QUERY_RESULT = {
    "kind": "complex_query",
    "short_answer": "Refund SLA was breached on 2 of 5 cases last week.",
    "reasoning_plan": ["List refund cases", "Check resolution timestamps vs SLA"],
    "evidence_refs": ["case_1", "case_2"],
    "affected_entities": ["case_1", "case_2"],
    "confidence": 0.78,
    "restricted_evidence_count": 1,
    "recommended_action": "Review the routing rule for high-value refunds.",
    "follow_up_questions": ["Which agent handled the breached cases?"],
}


# --- launch -----------------------------------------------------------------


def test_launch_posts_mode_and_embeds_sync_result():
    captured: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        captured.append(req)
        return httpx.Response(
            200,
            json={
                "job_id": "ctxjob_99",
                "status": "succeeded",
                "mode": "sync",
                "deduplicated": False,
                "result": COMPLEX_QUERY_RESULT,
            },
        )

    inv = _client(handler)
    out = inv.cortex.jobs.launch(
        project_id="proj_1",
        job_kind="complex_query",
        target_type="project",
        target_ref="proj_1",
        question="Were refund SLAs met last week?",
        mode="sync",
        idempotency_key="idem_1",
    )
    assert captured[0].method == "POST"
    assert captured[0].url.path == "/v1/cortex/jobs/launch"
    body = json.loads(captured[0].content)
    assert body["mode"] == "sync"
    assert body["job_kind"] == "complex_query"
    assert body["idempotency_key"] == "idem_1"
    assert out["status"] == "succeeded"
    assert out["result"]["kind"] == "complex_query"


def test_launch_async_returns_queued_with_no_result():
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "job_id": "ctxjob_async",
                "status": "queued",
                "mode": "async",
                "deduplicated": False,
            },
        )

    inv = _client(handler)
    out = inv.cortex.jobs.launch(
        project_id="proj_1",
        job_kind="workflow_eval",
        target_type="run",
        target_ref="run_1",
        mode="async",
    )
    assert out["status"] == "queued"
    assert out["mode"] == "async"
    assert "result" not in out


# --- list / retry / runs ----------------------------------------------------


def test_list_with_status_and_kind_filters():
    captured: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        captured.append(req)
        return httpx.Response(
            200,
            json={"data": [{"id": "ctxjob_1", "status": "succeeded"}], "next_cursor": None},
        )

    inv = _client(handler)
    out = inv.cortex.jobs.list(status="succeeded", kind="complex_query")
    assert captured[0].url.path == "/v1/cortex/jobs"
    qs = dict(captured[0].url.params)
    assert qs["status"] == "succeeded"
    assert qs["kind"] == "complex_query"
    assert out["data"][0]["id"] == "ctxjob_1"
    assert out["next_cursor"] is None


def test_retry_posts_to_retry_path():
    captured: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        captured.append(req)
        return httpx.Response(200, json={"job_id": "ctxjob_1", "status": "queued"})

    inv = _client(handler)
    out = inv.cortex.jobs.retry("ctxjob_1")
    assert captured[0].method == "POST"
    assert captured[0].url.path == "/v1/cortex/jobs/ctxjob_1/retry"
    assert out["status"] == "queued"


def test_runs_lists_attempt_history():
    captured: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        captured.append(req)
        return httpx.Response(
            200,
            json={"runs": [{"id": "run_1", "job_id": "ctxjob_1", "status": "succeeded"}]},
        )

    inv = _client(handler)
    out = inv.cortex.jobs.runs("ctxjob_1")
    assert captured[0].method == "GET"
    assert captured[0].url.path == "/v1/cortex/jobs/ctxjob_1/runs"
    assert out["runs"][0]["status"] == "succeeded"


# --- result parsing of the new kinds ----------------------------------------


def test_result_parses_complex_query():
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"job_id": "ctxjob_1", "status": "succeeded", "result": COMPLEX_QUERY_RESULT},
        )

    inv = _client(handler)
    out = inv.cortex.jobs.result("ctxjob_1")
    r = out["result"]
    assert r["kind"] == "complex_query"
    assert r["evidence_refs"] == ["case_1", "case_2"]
    assert r["restricted_evidence_count"] == 1


def test_result_parses_divergence_error_tracking():
    div = {
        "kind": "divergence_error_tracking",
        "target_type": "run",
        "target_ref": "run_1",
        "total_divergences": 3,
        "open_divergences": 2,
        "critical_open_divergences": 1,
        "by_kind": {"schema_violation": 2, "policy_violation": 1},
        "by_severity": {"high": 1, "medium": 2},
        "by_status": {"open": 2, "resolved": 1},
        "affected_run_ids": ["run_1"],
        "top_errors": [
            {
                "run_id": "run_1",
                "kind": "schema_violation",
                "severity": "high",
                "status": "open",
                "title": "Missing field",
                "summary": "Output lacked required `total`.",
                "suggested_action": "Add validation.",
            }
        ],
        "recommended_actions": ["Tighten output schema"],
    }

    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"job_id": "ctxjob_1", "status": "succeeded", "result": div},
        )

    inv = _client(handler)
    out = inv.cortex.jobs.result("ctxjob_1")
    r = out["result"]
    assert r["kind"] == "divergence_error_tracking"
    assert r["open_divergences"] == 2
    assert r["top_errors"][0]["title"] == "Missing field"


# --- wait_for_result --------------------------------------------------------


def test_wait_for_result_polls_until_terminal(monkeypatch):
    seq = [
        {"job_id": "ctxjob_1", "status": "running"},
        {"job_id": "ctxjob_1", "status": "running"},
        {"job_id": "ctxjob_1", "status": "succeeded", "result": COMPLEX_QUERY_RESULT},
    ]
    i = {"n": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        body = seq[min(i["n"], len(seq) - 1)]
        i["n"] += 1
        return httpx.Response(200, json=body)

    inv = _client(handler)
    monkeypatch.setattr("time.sleep", lambda _s: None)
    out = inv.cortex.jobs.wait_for_result("ctxjob_1", interval=0.01, timeout=5.0)
    assert out["status"] == "succeeded"
    assert out["result"]["kind"] == "complex_query"


def test_wait_for_result_raises_on_timeout(monkeypatch):
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"job_id": "ctxjob_1", "status": "running"})

    inv = _client(handler)
    monkeypatch.setattr("time.sleep", lambda _s: None)
    with pytest.raises(TimeoutError, match="did not finish"):
        inv.cortex.jobs.wait_for_result("ctxjob_1", interval=10.0, timeout=0.001)


# --- ask --------------------------------------------------------------------


def test_ask_sync_returns_parsed_result():
    captured: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        captured.append(req)
        return httpx.Response(
            200,
            json={
                "job_id": "ctxjob_ask",
                "status": "succeeded",
                "mode": "sync",
                "deduplicated": False,
                "result": COMPLEX_QUERY_RESULT,
            },
        )

    inv = _client(handler)
    out = inv.cortex.ask("Were refund SLAs met last week?", project_id="proj_1")
    assert captured[0].url.path == "/v1/cortex/jobs/launch"
    body = json.loads(captured[0].content)
    assert body["job_kind"] == "complex_query"
    assert body["target_type"] == "project"
    assert body["target_ref"] == "proj_1"
    assert body["mode"] == "sync"
    assert out["short_answer"].startswith("Refund SLA")
    assert out["evidence_refs"] == ["case_1", "case_2"]


def test_ask_async_polls_for_result(monkeypatch):
    captured: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        captured.append(req)
        if req.method == "POST":
            return httpx.Response(
                200,
                json={
                    "job_id": "ctxjob_ask",
                    "status": "queued",
                    "mode": "async",
                    "deduplicated": False,
                },
            )
        return httpx.Response(
            200,
            json={"job_id": "ctxjob_ask", "status": "succeeded", "result": COMPLEX_QUERY_RESULT},
        )

    inv = _client(handler)
    monkeypatch.setattr("time.sleep", lambda _s: None)
    out = inv.cortex.ask(
        "Anchor on a run",
        project_id="proj_1",
        target_type="run",
        target_ref="run_1",
        mode="async",
        poll_interval=0.01,
    )
    assert any(c.method == "GET" and c.url.path.endswith("/result") for c in captured)
    assert out["kind"] == "complex_query"


def test_ask_raises_clear_error_on_failure():
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "job_id": "ctxjob_ask",
                "status": "failed",
                "mode": "sync",
                "deduplicated": False,
                "error": "tool runtime disabled",
            },
        )

    inv = _client(handler)
    with pytest.raises(RuntimeError, match="failed: tool runtime disabled"):
        inv.cortex.ask("q", project_id="proj_1")


# --- async parity -----------------------------------------------------------


@pytest.mark.asyncio
async def test_async_launch_and_ask_sync():
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "job_id": "ctxjob_a",
                "status": "succeeded",
                "mode": "sync",
                "deduplicated": False,
                "result": COMPLEX_QUERY_RESULT,
            },
        )

    inv = _async_client(handler)
    try:
        launched = await inv.cortex.jobs.launch(
            project_id="proj_1",
            job_kind="complex_query",
            target_type="project",
            target_ref="proj_1",
            question="q",
            mode="sync",
        )
        assert launched["result"]["kind"] == "complex_query"
        asked = await inv.cortex.ask("q", project_id="proj_1")
        assert asked["short_answer"].startswith("Refund SLA")
    finally:
        await inv.aclose()


@pytest.mark.asyncio
async def test_async_list_retry_runs():
    def handler(req: httpx.Request) -> httpx.Response:
        path = req.url.path
        if path == "/v1/cortex/jobs":
            return httpx.Response(
                200, json={"data": [{"id": "ctxjob_1", "status": "succeeded"}], "next_cursor": None}
            )
        if path.endswith("/retry"):
            return httpx.Response(200, json={"job_id": "ctxjob_1", "status": "queued"})
        if path.endswith("/runs"):
            return httpx.Response(
                200, json={"runs": [{"id": "run_1", "job_id": "ctxjob_1", "status": "succeeded"}]}
            )
        return httpx.Response(404, json={})

    inv = _async_client(handler)
    try:
        listed = await inv.cortex.jobs.list(status="succeeded", kind="complex_query")
        assert listed["data"][0]["id"] == "ctxjob_1"
        retried = await inv.cortex.jobs.retry("ctxjob_1")
        assert retried["status"] == "queued"
        runs = await inv.cortex.jobs.runs("ctxjob_1")
        assert runs["runs"][0]["status"] == "succeeded"
    finally:
        await inv.aclose()


@pytest.mark.asyncio
async def test_async_wait_for_result_timeout(monkeypatch):
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"job_id": "ctxjob_1", "status": "running"})

    inv = _async_client(handler)

    async def _no_sleep(_s):
        return None

    monkeypatch.setattr("asyncio.sleep", _no_sleep)
    try:
        with pytest.raises(TimeoutError, match="did not finish"):
            await inv.cortex.jobs.wait_for_result("ctxjob_1", interval=10.0, timeout=0.001)
    finally:
        await inv.aclose()
