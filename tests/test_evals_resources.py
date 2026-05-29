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


def test_cases_from_run_forwards_signal_and_finding_provenance():
    calls: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else None
        calls.append({"path": request.url.path, "body": body})
        return httpx.Response(201, json={"case": {"id": "ec_3", "source_signal_id": "sig_1"}})

    inv = _inv_with_handler(handler)
    created = inv.evals.cases.create_from_run(
        "su_1",
        source_run_id="run_x",
        source_signal_id="sig_1",
        source_finding_id="fnd_1",
    )
    assert created["source_signal_id"] == "sig_1"
    assert calls[0]["body"] == {
        "source_run_id": "run_x",
        "source_finding_id": "fnd_1",
        "source_signal_id": "sig_1",
    }


def test_seed_suite_posts_to_server_seed_suite_endpoint():
    calls: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else None
        calls.append({"method": request.method, "path": request.url.path, "body": body})
        if request.url.path == "/v1/eval-datasets/seed-suite":
            return httpx.Response(
                201,
                json={
                    "dataset": {"id": "ds_1", "name": body["name"]},
                    "suite": {"id": "su_1", "name": body["name"]},
                    "examples": [{"id": "ex_1"}, {"id": "ex_2"}],
                    "cases": [{"id": "ec_1"}, {"id": "ec_2"}],
                    "eval_run": {"id": "erun_1", "status": "queued"},
                },
            )
        return httpx.Response(404)

    inv = _inv_with_handler(handler)
    seeded = inv.evals.seed_suite(
        name="refund-regression",
        run=True,
        rows=[
            {
                "name": "approved",
                "input": {"prompt": "approve refund"},
                "expected": {"assertions": [{"path": "outcome", "op": "equals", "value": "approved"}]},
            },
            {
                "input": {"prompt": "deny refund"},
                "expected": {"assertions": [{"path": "outcome", "op": "equals", "value": "denied"}]},
                "mutations": [{"kind": "replace_prompt", "value": "deny refund without approval"}],
            },
        ],
    )

    assert [c["path"] for c in calls] == ["/v1/eval-datasets/seed-suite"]
    assert calls[0]["body"] == {
        "name": "refund-regression",
        "description": None,
        "target_type": "custom",
        "dataset_metadata": None,
        "suite_metadata": None,
        "rows": [
            {
                "name": "approved",
                "input": {"prompt": "approve refund"},
                "expected": {"assertions": [{"path": "outcome", "op": "equals", "value": "approved"}]},
                "assertions": None,
                "mutations": None,
                "metadata": None,
            },
            {
                "name": "case-002",
                "input": {"prompt": "deny refund"},
                "expected": {"assertions": [{"path": "outcome", "op": "equals", "value": "denied"}]},
                "assertions": None,
                "mutations": [{"kind": "replace_prompt", "value": "deny refund without approval"}],
                "metadata": None,
            },
        ],
        "run": True,
    }
    assert seeded["dataset_id"] == "ds_1"
    assert seeded["suite_id"] == "su_1"
    assert seeded["case_count"] == 2
    assert seeded["eval_run"]["id"] == "erun_1"


def test_seed_suite_with_different_suite_name_falls_back_to_client_orchestration():
    calls: list[dict] = []
    example_count = 0
    case_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal example_count, case_count
        body = json.loads(request.content) if request.content else None
        calls.append({"method": request.method, "path": request.url.path, "body": body})
        if request.url.path == "/v1/eval-datasets":
            return httpx.Response(201, json={"dataset": {"id": "ds_1", "name": body["name"]}})
        if request.url.path == "/v1/eval-suites":
            return httpx.Response(201, json={"suite": {"id": "su_1", "name": body["name"]}})
        if request.url.path == "/v1/eval-datasets/ds_1/examples":
            example_count += 1
            return httpx.Response(
                201,
                json={"example": {"id": f"ex_{example_count}", "dataset_id": "ds_1"}},
            )
        if request.url.path == "/v1/eval-suites/su_1/cases":
            case_count += 1
            return httpx.Response(
                201,
                json={"case": {"id": f"ec_{case_count}", "suite_id": "su_1"}},
            )
        if request.url.path == "/v1/eval-suites/su_1/run":
            return httpx.Response(201, json={"eval_run": {"id": "erun_1", "status": "queued"}})
        return httpx.Response(404)

    inv = _inv_with_handler(handler)
    seeded = inv.evals.seed_suite(
        name="refund-regression-dataset",
        suite_name="refund-regression-suite",
        run=True,
        rows=[
            {
                "name": "approved",
                "input": {"prompt": "approve refund"},
                "expected": {"assertions": [{"path": "outcome", "op": "equals", "value": "approved"}]},
            },
        ],
    )

    assert [c["path"] for c in calls] == [
        "/v1/eval-datasets",
        "/v1/eval-suites",
        "/v1/eval-datasets/ds_1/examples",
        "/v1/eval-suites/su_1/cases",
        "/v1/eval-suites/su_1/run",
    ]
    assert calls[1]["body"] == {
        "name": "refund-regression-suite",
        "target_type": "custom",
        "dataset_id": "ds_1",
    }
    assert calls[3]["body"] == {
        "name": "approved",
        "dataset_example_id": "ex_1",
        "input_bundle": {"prompt": "approve refund"},
        "expected": {"assertions": [{"path": "outcome", "op": "equals", "value": "approved"}]},
    }
    assert seeded["dataset_id"] == "ds_1"
    assert seeded["suite_id"] == "su_1"
    assert seeded["case_count"] == 1
    assert seeded["eval_run"]["id"] == "erun_1"


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
    assert hasattr(inv.evals, "seed_suite")
