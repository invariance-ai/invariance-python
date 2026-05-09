"""Tests for EvalsResource and AsyncEvalsResource."""

from __future__ import annotations

import json

import httpx
import pytest

from invariance import AsyncInvariance, Invariance, derive_status, read_eval_metadata


def _inv_with_handler(handler):
    transport = httpx.MockTransport(handler)
    inv = Invariance(api_key="inv_test", api_url="http://test.local")
    inv._http._client = httpx.Client(
        base_url="http://test.local",
        headers={"Authorization": "Bearer inv_test"},
        transport=transport,
    )
    return inv


def _async_inv_with_handler(handler):
    transport = httpx.MockTransport(handler)
    inv = AsyncInvariance(api_key="inv_test", api_url="http://test.local")
    inv._http._client = httpx.AsyncClient(
        base_url="http://test.local",
        headers={"Authorization": "Bearer inv_test"},
        transport=transport,
    )
    return inv


def test_derive_status_pass_when_no_qualifying_findings():
    findings = [
        {"id": "f1", "severity": "low", "status": "open"},
        {"id": "f2", "severity": "medium", "status": "resolved"},
        {"id": "f3", "severity": "high", "status": "dismissed"},
    ]
    assert derive_status(findings) == "pass"


def test_derive_status_fail_on_open_medium():
    findings = [{"id": "f1", "severity": "medium", "status": "open"}]
    assert derive_status(findings) == "fail"


def test_derive_status_fail_on_review_requested_critical():
    findings = [{"id": "f1", "severity": "critical", "status": "review_requested"}]
    assert derive_status(findings) == "fail"


def test_read_eval_metadata_extracts_suite_and_case():
    md = {"eval": {"suite": "refund-flow", "case": "happy-path", "tags": ["p0"]}}
    meta = read_eval_metadata(md)
    assert meta == {"suite": "refund-flow", "case": "happy-path", "tags": ["p0"]}


def test_read_eval_metadata_returns_none_without_eval_key():
    assert read_eval_metadata({"other": 1}) is None
    assert read_eval_metadata(None) is None
    assert read_eval_metadata({"eval": {"suite": "x"}}) is None  # missing case


def test_run_case_creates_run_with_eval_metadata_and_returns_pass():
    posted_runs = []

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if request.method == "POST" and path == "/v1/runs":
            body = json.loads(request.content)
            posted_runs.append(body)
            return httpx.Response(
                200,
                json={"run": {"id": "run_eval_1", "name": body.get("name"), "status": "running"}},
            )
        if request.method == "PATCH" and path == "/v1/runs/run_eval_1":
            return httpx.Response(200, json={"run": {"id": "run_eval_1", "status": "completed"}})
        if request.method == "GET" and path == "/v1/findings":
            return httpx.Response(200, json={"data": [], "next_cursor": None})
        return httpx.Response(404, json={"error": {"code": "not_found", "message": path}})

    inv = _inv_with_handler(handler)
    handler_calls = []

    def case_handler(run):
        handler_calls.append(run.run_id)

    res = inv.evals.run_case(
        suite="refund-flow",
        case="happy-path",
        handler=case_handler,
        expected={"refund_id": "rf_1"},
        tags=["p0"],
    )

    assert handler_calls == ["run_eval_1"]
    assert posted_runs[0]["name"] == "eval:refund-flow:happy-path"
    assert posted_runs[0]["metadata"]["eval"] == {
        "suite": "refund-flow",
        "case": "happy-path",
        "expected": {"refund_id": "rf_1"},
        "tags": ["p0"],
    }
    assert res["run_id"] == "run_eval_1"
    assert res["status"] == "pass"
    assert res["findings"] == []


def test_run_case_fails_status_when_findings_open_medium():
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if request.method == "POST" and path == "/v1/runs":
            return httpx.Response(200, json={"run": {"id": "run_x", "status": "running"}})
        if request.method == "PATCH":
            return httpx.Response(200, json={"run": {"id": "run_x", "status": "completed"}})
        if path == "/v1/findings":
            return httpx.Response(
                200,
                json={
                    "data": [
                        {"id": "f1", "severity": "medium", "status": "open"},
                    ],
                    "next_cursor": None,
                },
            )
        return httpx.Response(404, json={"error": {"code": "x", "message": path}})

    inv = _inv_with_handler(handler)
    res = inv.evals.run_case(suite="s", case="c", handler=lambda r: None)
    assert res["status"] == "fail"


def test_run_case_evaluates_monitors_when_provided():
    seen_paths = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_paths.append((request.method, request.url.path))
        path = request.url.path
        if request.method == "POST" and path == "/v1/runs":
            return httpx.Response(200, json={"run": {"id": "run_m", "status": "running"}})
        if request.method == "PATCH":
            return httpx.Response(200, json={"run": {"id": "run_m", "status": "completed"}})
        if request.method == "POST" and path.startswith("/v1/monitors/"):
            return httpx.Response(
                200,
                json={"monitor_id": "mon_1", "evaluated_at": "t", "signals_emitted": 0},
            )
        if path == "/v1/findings":
            return httpx.Response(200, json={"data": [], "next_cursor": None})
        return httpx.Response(404, json={"error": {"code": "x", "message": path}})

    inv = _inv_with_handler(handler)
    inv.evals.run_case(
        suite="s", case="c", handler=lambda r: None, monitor_ids=["mon_1", "mon_2"]
    )
    eval_paths = [p for m, p in seen_paths if m == "POST" and p.startswith("/v1/monitors/")]
    assert "/v1/monitors/mon_1/evaluate" in eval_paths
    assert "/v1/monitors/mon_2/evaluate" in eval_paths


def test_list_cases_filters_by_suite_and_skips_non_eval_runs():
    seen_params = {}

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/v1/runs":
            seen_params.update(dict(request.url.params))
            return httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "id": "run_a",
                            "created_at": "2026-05-08T00:00:00Z",
                            "metadata": {"eval": {"suite": "s", "case": "c1"}},
                        },
                        {
                            "id": "run_b",
                            "created_at": "2026-05-08T00:01:00Z",
                            "metadata": {"other": 1},  # not an eval — skipped
                        },
                    ],
                    "next_cursor": None,
                },
            )
        if path == "/v1/findings":
            return httpx.Response(200, json={"data": [], "next_cursor": None})
        return httpx.Response(404, json={"error": {"code": "x", "message": path}})

    inv = _inv_with_handler(handler)
    res = inv.evals.list_cases(suite="s", limit=10)
    assert seen_params["eval_suite"] == "s"
    assert seen_params["limit"] == "10"
    assert len(res["runs"]) == 1
    assert res["runs"][0]["case"] == "c1"
    assert res["runs"][0]["status"] == "pass"


def test_summarize_aggregates_pass_fail_counts():
    findings_by_run = {
        "run_pass": [],
        "run_fail": [{"id": "f", "severity": "high", "status": "open"}],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/v1/runs":
            return httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "id": "run_pass",
                            "created_at": "t",
                            "metadata": {"eval": {"suite": "s", "case": "p"}},
                        },
                        {
                            "id": "run_fail",
                            "created_at": "t",
                            "metadata": {"eval": {"suite": "s", "case": "f"}},
                        },
                    ],
                    "next_cursor": None,
                },
            )
        if path == "/v1/findings":
            run_id = request.url.params.get("run_id", "")
            return httpx.Response(
                200, json={"data": findings_by_run.get(run_id, []), "next_cursor": None}
            )
        return httpx.Response(404, json={"error": {"code": "x", "message": path}})

    inv = _inv_with_handler(handler)
    summary = inv.evals.summarize("s")
    assert summary == {"suite": "s", "total": 2, "passed": 1, "failed": 1}


@pytest.mark.asyncio
async def test_async_run_case_supports_async_handler():
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if request.method == "POST" and path == "/v1/runs":
            return httpx.Response(200, json={"run": {"id": "run_a", "status": "running"}})
        if request.method == "PATCH":
            return httpx.Response(200, json={"run": {"id": "run_a", "status": "completed"}})
        if path == "/v1/findings":
            return httpx.Response(200, json={"data": [], "next_cursor": None})
        return httpx.Response(404, json={"error": {"code": "x", "message": path}})

    inv = _async_inv_with_handler(handler)
    try:
        called = []

        async def case_handler(run):
            called.append(run.run_id)

        res = await inv.evals.run_case(suite="s", case="c", handler=case_handler)
        assert called == ["run_a"]
        assert res["status"] == "pass"
        assert res["run_id"] == "run_a"
    finally:
        await inv.aclose()
