"""Tests for new EvalsResource sub-resources: datasets, scorers, suites, cases, eval_runs."""

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


def test_datasets_create_posts_body_and_unwraps():
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["path"] = request.url.path
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            201,
            json={"dataset": {"id": "ds_1", "name": "smoke", "description": "", "agent_id": "a", "metadata": {}, "created_at": "t", "updated_at": "t"}},
        )

    inv = _inv_with_handler(handler)
    ds = inv.evals.datasets.create(name="smoke", description="d", metadata={"k": "v"})
    assert seen["method"] == "POST"
    assert seen["path"] == "/v1/eval-datasets"
    assert seen["body"] == {"name": "smoke", "description": "d", "metadata": {"k": "v"}}
    assert ds["id"] == "ds_1"


def test_datasets_list_passes_query():
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["params"] = dict(request.url.params)
        return httpx.Response(200, json={"data": [], "next_cursor": None})

    inv = _inv_with_handler(handler)
    inv.evals.datasets.list(limit=10, cursor="c1")
    assert seen["params"] == {"limit": "10", "cursor": "c1"}


def test_datasets_get_and_append_example():
    calls: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else None
        calls.append({"method": request.method, "path": request.url.path, "body": body})
        if request.url.path == "/v1/eval-datasets/ds_1":
            return httpx.Response(200, json={"dataset": {"id": "ds_1"}})
        return httpx.Response(201, json={"example": {"id": "ex_1", "dataset_id": "ds_1"}})

    inv = _inv_with_handler(handler)
    inv.evals.datasets.get("ds_1")
    ex = inv.evals.datasets.append_example("ds_1", input={"q": "hi"}, expected={"a": "ok"})
    assert calls[0]["path"] == "/v1/eval-datasets/ds_1"
    assert calls[1]["method"] == "POST"
    assert calls[1]["path"] == "/v1/eval-datasets/ds_1/examples"
    assert calls[1]["body"] == {"input": {"q": "hi"}, "expected": {"a": "ok"}}
    assert ex["id"] == "ex_1"


def test_scorers_create_and_list():
    calls: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else None
        calls.append({"method": request.method, "path": request.url.path, "body": body, "params": dict(request.url.params)})
        if request.method == "POST":
            return httpx.Response(201, json={"scorer": {"id": "sc_1", "name": "exact", "kind": "builtin"}})
        return httpx.Response(200, json={"data": [], "next_cursor": None})

    inv = _inv_with_handler(handler)
    sc = inv.evals.scorers.create(name="exact", kind="builtin", definition={"op": "equals"})
    inv.evals.scorers.list()
    assert calls[0]["path"] == "/v1/eval-scorers"
    assert calls[0]["body"] == {"name": "exact", "kind": "builtin", "definition": {"op": "equals"}}
    assert sc["id"] == "sc_1"
    assert calls[1]["path"] == "/v1/eval-scorers"


def test_suites_create_get_run():
    calls: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else None
        calls.append({"method": request.method, "path": request.url.path, "body": body})
        if request.url.path == "/v1/eval-suites" and request.method == "POST":
            return httpx.Response(201, json={"suite": {"id": "su_1"}})
        if request.url.path == "/v1/eval-suites/su_1":
            return httpx.Response(200, json={"suite": {"id": "su_1"}})
        if request.url.path == "/v1/eval-suites/su_1/run":
            return httpx.Response(201, json={"eval_run": {"id": "er_1", "status": "queued"}})
        return httpx.Response(404)

    inv = _inv_with_handler(handler)
    inv.evals.suites.create(name="s", target_type="agent", scorer_ids=["sc_1"])
    inv.evals.suites.get("su_1")
    er = inv.evals.suites.run("su_1", metadata={"trigger": "test"})
    assert calls[0]["body"] == {"name": "s", "target_type": "agent", "scorer_ids": ["sc_1"]}
    assert calls[2]["body"] == {"metadata": {"trigger": "test"}}
    assert er["id"] == "er_1"


def test_cases_create_and_from_run_and_list():
    calls: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else None
        calls.append({"method": request.method, "path": request.url.path, "body": body})
        if request.url.path.endswith("/cases/from-run"):
            return httpx.Response(201, json={"case": {"id": "ec_2"}})
        if request.method == "POST":
            return httpx.Response(201, json={"case": {"id": "ec_1"}})
        return httpx.Response(200, json={"data": [], "next_cursor": None})

    inv = _inv_with_handler(handler)
    inv.evals.cases.create("su_1", name="c1", input_bundle={"x": 1})
    inv.evals.cases.create_from_run("su_1", source_run_id="run_x", name="cf")
    inv.evals.cases.list("su_1", limit=5)
    assert calls[0]["path"] == "/v1/eval-suites/su_1/cases"
    assert calls[1]["path"] == "/v1/eval-suites/su_1/cases/from-run"
    assert calls[1]["body"] == {"source_run_id": "run_x", "name": "cf"}
    assert calls[2]["path"] == "/v1/eval-suites/su_1/cases"


def test_eval_runs_get_and_results():
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
        if request.url.path == "/v1/eval-runs/er_1":
            return httpx.Response(200, json={"eval_run": {"id": "er_1", "status": "succeeded"}})
        return httpx.Response(200, json={"data": [{"id": "res_1", "status": "passed"}], "next_cursor": None})

    inv = _inv_with_handler(handler)
    er = inv.evals.eval_runs.get("er_1")
    res = inv.evals.eval_runs.list_results("er_1", limit=20)
    assert er["id"] == "er_1"
    assert res["data"][0]["id"] == "res_1"
    assert seen == ["/v1/eval-runs/er_1", "/v1/eval-runs/er_1/results"]


def test_scorers_list_builtins_hits_v1_scorers():
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        return httpx.Response(200, json={"data": [{"name": "exact_match", "description": "d"}]})

    inv = _inv_with_handler(handler)
    res = inv.evals.scorers.list_builtins()
    assert seen["path"] == "/v1/scorers"
    assert res["data"][0]["name"] == "exact_match"


def test_experiments_run_posts_scorer_specs():
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["path"] = request.url.path
        seen["body"] = json.loads(request.content)
        return httpx.Response(201, json={"eval_run": {"id": "er_1", "status": "running"}})

    inv = _inv_with_handler(handler)
    er = inv.evals.experiments.run(
        "er_1",
        scorer_specs=[{"name": "exact_match"}, {"name": "numeric_tolerance", "config": {"tolerance": 0.1}}],
        baseline_run_id="er_0",
    )
    assert seen["method"] == "POST"
    assert seen["path"] == "/v1/eval-runs/er_1/experiment"
    assert seen["body"] == {
        "scorer_specs": [
            {"name": "exact_match"},
            {"name": "numeric_tolerance", "config": {"tolerance": 0.1}},
        ],
        "baseline_run_id": "er_0",
    }
    assert er["id"] == "er_1"


def test_experiments_compare_passes_baseline_query():
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["params"] = dict(request.url.params)
        return httpx.Response(
            200,
            json={
                "run_id": "er_1",
                "baseline_run_id": "er_0",
                "aggregate": [{"scorer": "exact_match", "baseline": 0.5, "current": 0.8, "delta": 0.3}],
                "cases": [],
            },
        )

    inv = _inv_with_handler(handler)
    res = inv.evals.experiments.compare("er_1", baseline_run_id="er_0")
    assert seen["path"] == "/v1/eval-runs/er_1/compare"
    assert seen["params"] == {"baseline": "er_0"}
    assert res["aggregate"][0]["delta"] == 0.3


# Async smoke — confirm AsyncEvalsResource exposes the sub-resources.

def test_async_evals_has_sub_resources():
    from invariance import AsyncInvariance

    inv = AsyncInvariance(api_key="inv_test", api_url="http://test.local")
    assert hasattr(inv.evals, "datasets")
    assert hasattr(inv.evals, "scorers")
    assert hasattr(inv.evals, "suites")
    assert hasattr(inv.evals, "cases")
    assert hasattr(inv.evals, "eval_runs")
    assert hasattr(inv.evals, "experiments")
