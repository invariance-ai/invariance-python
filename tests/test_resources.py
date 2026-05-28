"""Tests for ProofsResource, FindingsResource, ReviewsResource."""

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


def test_proofs_verify_run_hits_expected_path():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/v1/runs/run_1/verify"
        return httpx.Response(
            200,
            json={"run_id": "run_1", "valid": True, "node_count": 3, "head_hash": "h", "first_invalid_node_id": None, "reason": None},
        )

    inv = _inv_with_handler(handler)
    res = inv.proofs.verify_run("run_1")
    assert res["valid"] is True
    assert res["node_count"] == 3


def test_runs_operational_graph_hits_expected_path():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/v1/runs/run_1/operational-graph"
        return httpx.Response(
            200,
            json={
                "run_id": "run_1",
                "entities": [
                    {
                        "id": "ent_1",
                        "kind": "business_object",
                        "source": "stripe",
                        "title": "Refund re_1",
                        "attributes": {},
                        "created_at": "t",
                    }
                ],
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

    inv = _inv_with_handler(handler)
    graph = inv.runs.operational_graph("run_1")
    assert graph["run_id"] == "run_1"
    assert graph["completeness"]["score"] == 0.2
    assert len(graph["entities"]) == 1
    assert graph["entities"][0]["kind"] == "business_object"


def test_runs_inspect_returns_observability_summary():
    seen_paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_paths.append(str(request.url))
        if request.method == "GET" and request.url.path == "/v1/runs/run_1":
            return httpx.Response(
                200,
                json={
                    "run": {
                        "id": "run_1",
                        "agent_id": "a_1",
                        "name": "demo",
                        "status": "completed",
                        "metadata": {},
                        "created_at": "2026-05-28T00:00:00Z",
                        "updated_at": "2026-05-28T00:00:00Z",
                        "closed_at": "2026-05-28T00:01:00Z",
                    }
                },
            )
        if request.method == "GET" and request.url.path == "/v1/runs/run_1/nodes":
            assert request.url.params["limit"] == "25"
            return httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "id": "node_llm",
                            "run_id": "run_1",
                            "agent_id": "a_1",
                            "parent_id": None,
                            "action_type": "llm.complete",
                            "type": "llm_call",
                            "input": None,
                            "output": {"text": "Created useful observability output."},
                            "error": None,
                            "metadata": {
                                "llm": {
                                    "input_tokens": 100,
                                    "output_tokens": 25,
                                    "cache_read_tokens": 5,
                                },
                                "words_created": 4,
                            },
                            "custom_fields": {},
                            "timestamp": 1,
                            "duration_ms": 250,
                            "hash": "h1",
                            "previous_hashes": [],
                            "signature": None,
                            "created_at": "2026-05-28T00:00:00Z",
                            "handoff_from": None,
                            "handoff_to": None,
                            "handoff_reason": None,
                        },
                        {
                            "id": "node_tool",
                            "run_id": "run_1",
                            "agent_id": "a_1",
                            "parent_id": "node_llm",
                            "action_type": "stripe.refunds.create",
                            "type": "tool_call",
                            "input": {},
                            "output": {},
                            "error": None,
                            "metadata": {"tool_name": "stripe.refunds.create"},
                            "custom_fields": {},
                            "timestamp": 2,
                            "duration_ms": 125,
                            "hash": "h2",
                            "previous_hashes": ["h1"],
                            "signature": None,
                            "created_at": "2026-05-28T00:00:01Z",
                            "handoff_from": None,
                            "handoff_to": None,
                            "handoff_reason": None,
                        },
                    ],
                    "next_cursor": None,
                },
            )
        return httpx.Response(404, json={"error": {"code": "nf", "message": "nf"}})

    inv = _inv_with_handler(handler)
    result = inv.runs.inspect("run_1", limit=25, include_operational_graph=False)

    assert result["run"]["id"] == "run_1"
    assert result["observability"]["step_count"] == 2
    assert result["observability"]["llm_call_count"] == 1
    assert result["observability"]["tool_call_count"] == 1
    assert result["observability"]["total_input_tokens"] == 100
    assert result["observability"]["total_output_tokens"] == 25
    assert result["observability"]["total_cache_read_tokens"] == 5
    assert result["observability"]["total_words_created"] == 4
    assert result["observability"]["total_duration_ms"] == 375
    assert [step["kind"] for step in result["observability"]["steps"]] == ["llm", "tool"]
    assert result["operational_graph"] is None
    assert any("/v1/runs/run_1/nodes?limit=25" in path for path in seen_paths)


def test_findings_update_posts_status():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["path"] = request.url.path
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"finding": {"id": "f_1", "status": "resolved"}})

    inv = _inv_with_handler(handler)
    f = inv.findings.update("f_1", status="resolved")
    assert seen["method"] == "PATCH"
    assert seen["path"] == "/v1/findings/f_1"
    assert seen["body"] == {"status": "resolved"}
    assert f["status"] == "resolved"


def test_findings_list_params():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["params"] = dict(request.url.params)
        return httpx.Response(200, json={"data": [], "next_cursor": None})

    inv = _inv_with_handler(handler)
    inv.findings.list(limit=5, cursor="c_1")
    assert seen["params"] == {"cursor": "c_1", "limit": "5"}


def test_reviews_claim_and_resolve():
    calls: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append({"method": request.method, "path": request.url.path, "body": json.loads(request.content)})
        return httpx.Response(200, json={"review": {"id": "rv_1"}, "finding": {"id": "f_1"}})

    inv = _inv_with_handler(handler)
    inv.reviews.claim("rv_1", notes="mine")
    inv.reviews.resolve("rv_1", decision="passed", notes="looks ok")
    assert calls[0]["body"] == {"status": "claimed", "notes": "mine"}
    assert calls[1]["body"] == {"decision": "passed", "notes": "looks ok"}


# ── Memory ────────────────────────────────────────────────────────────────


def _memory_access(**overrides):
    base = {
        "id": "ma_1",
        "run_id": "r_1",
        "node_id": "n_1",
        "agent_id": "a_1",
        "access_type": "read",
        "subject_type": "customer",
        "subject_id": "cust_1",
        "key": "plan",
        "value": None,
        "used_for": "support",
        "source_node_id": None,
        "timestamp": "2026-05-10T00:00:00Z",
    }
    base.update(overrides)
    return base


def test_memory_read_passes_subject_and_used_for():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["path"] = request.url.path
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"access": _memory_access(), "record": None})

    inv = _inv_with_handler(handler)
    res = inv.memory.read(
        subject_type="customer",
        subject_id="cust_1",
        key="plan",
        used_for="support_reply",
        run_id="r_1",
        node_id="n_1",
    )
    assert seen["method"] == "POST"
    assert seen["path"] == "/v1/memory/read"
    assert seen["body"] == {
        "subject_type": "customer",
        "subject_id": "cust_1",
        "key": "plan",
        "used_for": "support_reply",
        "run_id": "r_1",
        "node_id": "n_1",
    }
    assert res["record"] is None


def test_memory_write_defaults_source_and_confidence():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "access": _memory_access(access_type="write", value="enterprise"),
                "record": {
                    "id": "mr_1",
                    "agent_id": "a_1",
                    "subject_type": "customer",
                    "subject_id": "cust_1",
                    "claim": "plan=enterprise",
                    "value": "enterprise",
                    "source": "agent_write",
                    "confidence": 1.0,
                    "valid_from": "2026-05-10T00:00:00Z",
                    "valid_until": None,
                    "last_verified_at": None,
                    "superseded_by": None,
                    "provenance": [],
                },
            },
        )

    inv = _inv_with_handler(handler)
    inv.memory.write(
        subject_type="customer",
        subject_id="cust_1",
        key="plan",
        value="enterprise",
        used_for="personalize",
        run_id="r_1",
    )
    assert seen["body"]["source"] == "agent_write"
    assert seen["body"]["confidence"] == 1.0
    assert seen["body"]["value"] == "enterprise"
    assert "node_id" not in seen["body"]


# ── Evals ─────────────────────────────────────────────────────────────────


def _run_response(run_id="run_eval", metadata=None):
    return {
        "run": {
            "id": run_id,
            "agent_id": "a_1",
            "name": "x",
            "status": "open",
            "metadata": metadata or {},
            "created_at": "2026-05-10T00:00:00Z",
            "updated_at": "2026-05-10T00:00:00Z",
            "closed_at": None,
            "parent_run_id": None,
            "fork_point_node_id": None,
            "replay_seed": None,
            "total_input_tokens": 0,
            "total_output_tokens": 0,
            "total_cache_read": 0,
            "total_cache_write": 0,
            "total_cost_usd": 0.0,
            "llm_call_count": 0,
            "tool_call_count": 0,
            "error_count": 0,
            "total_latency_ms": 0,
        }
    }


def test_evals_run_case_passes_when_no_findings():
    seen_findings_params: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        method = request.method
        if method == "POST" and path == "/v1/runs":
            return httpx.Response(200, json=_run_response())
        if method == "PATCH" and path == "/v1/runs/run_eval":
            return httpx.Response(200, json={"run": {"id": "run_eval", "status": "completed"}})
        if method == "GET" and path == "/v1/findings":
            seen_findings_params.append(dict(request.url.params))
            return httpx.Response(200, json={"data": [], "next_cursor": None})
        return httpx.Response(404)

    inv = _inv_with_handler(handler)
    result = inv.evals.run_case(suite="suite_a", case="case_1", handler=lambda run: None)
    assert result["status"] == "pass"
    assert result["run_id"] == "run_eval"
    assert any(p.get("run_id") == "run_eval" for p in seen_findings_params)


def test_evals_run_case_fails_on_high_severity_finding():
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        method = request.method
        if method == "POST" and path == "/v1/runs":
            return httpx.Response(200, json=_run_response())
        if method == "PATCH":
            return httpx.Response(200, json={"run": {"id": "run_eval", "status": "completed"}})
        if method == "GET" and path == "/v1/findings":
            return httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "id": "f1",
                            "agent_id": "a",
                            "monitor_id": "m",
                            "signal_id": "s",
                            "run_id": "run_eval",
                            "node_id": None,
                            "severity": "high",
                            "title": "bad",
                            "summary": "bad",
                            "status": "open",
                            "created_at": "t",
                            "updated_at": "t",
                        }
                    ],
                    "next_cursor": None,
                },
            )
        return httpx.Response(404)

    inv = _inv_with_handler(handler)
    result = inv.evals.run_case(suite="s", case="c", handler=lambda r: None)
    assert result["status"] == "fail"
    assert len(result["findings"]) == 1


def test_evals_list_cases_filters_by_eval_metadata():
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        method = request.method
        if method == "GET" and path == "/v1/runs":
            assert request.url.params.get("eval_suite") == "smoke"
            return httpx.Response(
                200,
                json={
                    "data": [
                        _run_response(run_id="r1", metadata={"eval": {"suite": "smoke", "case": "c1"}})["run"],
                        _run_response(run_id="r2", metadata={"other": "x"})["run"],
                    ],
                    "next_cursor": None,
                },
            )
        if method == "GET" and path == "/v1/findings":
            return httpx.Response(200, json={"data": [], "next_cursor": None})
        return httpx.Response(404)

    inv = _inv_with_handler(handler)
    res = inv.evals.list_cases(suite="smoke")
    assert len(res["runs"]) == 1
    assert res["runs"][0]["case"] == "c1"
    assert res["runs"][0]["status"] == "pass"
