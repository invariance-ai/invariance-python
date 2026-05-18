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
