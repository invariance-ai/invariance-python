"""Evals — run a handler as a tracked case, then derive pass/fail from findings."""

from __future__ import annotations

from typing import Any, Callable

from ._query import with_query
from ._types import (
    BuiltinScorerList,
    CompareResponse,
    EvalCase,
    EvalCaseList,
    EvalCaseRecord,
    EvalDataset,
    EvalDatasetExample,
    EvalDatasetExampleList,
    EvalDatasetList,
    EvalListResponse,
    EvalMetadata,
    EvalResult,
    EvalResultRowList,
    EvalRunRecord,
    EvalScorer,
    EvalScorerKind,
    EvalScorerList,
    EvalStatus,
    EvalSuiteList,
    EvalSuiteRecord,
    EvalSummary,
    EvalTargetType,
    Finding,
    ScorerSpec,
    SeedEvalSuiteResult,
    SeedEvalSuiteRow,
    Severity,
)
from .client import HttpClient
from .monitors import MonitorsResource
from .runs import Run, RunsResource


_SEVERITY_ORDER: dict[Severity, int] = {
    "info": 0,
    "low": 1,
    "medium": 2,
    "high": 3,
    "critical": 4,
}
_FAIL_THRESHOLD: Severity = "medium"


def read_eval_metadata(metadata: dict[str, Any] | None) -> EvalMetadata | None:
    if not metadata:
        return None
    e = metadata.get("eval")
    if not isinstance(e, dict):
        return None
    suite = e.get("suite")
    case = e.get("case")
    if not isinstance(suite, str) or not isinstance(case, str):
        return None
    out: EvalMetadata = {"suite": suite, "case": case}
    if "expected" in e:
        out["expected"] = e["expected"]
    if "inputs" in e:
        out["inputs"] = e["inputs"]
    tags = e.get("tags")
    if isinstance(tags, list):
        out["tags"] = [t for t in tags if isinstance(t, str)]
    return out


def derive_status(findings: list[Finding]) -> EvalStatus:
    threshold = _SEVERITY_ORDER[_FAIL_THRESHOLD]
    for f in findings:
        if f.get("status") not in ("open", "review_requested"):
            continue
        if _SEVERITY_ORDER.get(f["severity"], 0) >= threshold:
            return "fail"
    return "pass"


class DatasetsResource:
    def __init__(self, http: HttpClient) -> None:
        self._http = http

    def create(
        self,
        *,
        name: str,
        description: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> EvalDataset:
        body: dict[str, Any] = {"name": name}
        if description is not None:
            body["description"] = description
        if metadata is not None:
            body["metadata"] = metadata
        res = self._http.post("/v1/eval-datasets", body)
        return res["dataset"]

    def list(
        self,
        *,
        limit: int | None = None,
        cursor: str | None = None,
    ) -> EvalDatasetList:
        return self._http.get(with_query("/v1/eval-datasets", limit=limit, cursor=cursor))

    def get(self, dataset_id: str) -> EvalDataset:
        res = self._http.get(f"/v1/eval-datasets/{dataset_id}")
        return res["dataset"]

    def append_example(
        self,
        dataset_id: str,
        *,
        input: dict[str, Any],
        expected: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> EvalDatasetExample:
        body: dict[str, Any] = {"input": input}
        if expected is not None:
            body["expected"] = expected
        if metadata is not None:
            body["metadata"] = metadata
        res = self._http.post(f"/v1/eval-datasets/{dataset_id}/examples", body)
        return res["example"]

    def list_examples(
        self,
        dataset_id: str,
        *,
        limit: int | None = None,
        cursor: str | None = None,
    ) -> EvalDatasetExampleList:
        return self._http.get(
            with_query(f"/v1/eval-datasets/{dataset_id}/examples", limit=limit, cursor=cursor)
        )


class ScorersResource:
    def __init__(self, http: HttpClient) -> None:
        self._http = http

    def create(
        self,
        *,
        name: str,
        kind: EvalScorerKind,
        description: str | None = None,
        definition: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> EvalScorer:
        body: dict[str, Any] = {"name": name, "kind": kind}
        if description is not None:
            body["description"] = description
        if definition is not None:
            body["definition"] = definition
        if metadata is not None:
            body["metadata"] = metadata
        res = self._http.post("/v1/eval-scorers", body)
        return res["scorer"]

    def list(
        self,
        *,
        limit: int | None = None,
        cursor: str | None = None,
    ) -> EvalScorerList:
        return self._http.get(with_query("/v1/eval-scorers", limit=limit, cursor=cursor))

    def list_builtins(self) -> BuiltinScorerList:
        return self._http.get("/v1/scorers")


class ExperimentsResource:
    def __init__(self, http: HttpClient) -> None:
        self._http = http

    def run(
        self,
        eval_run_id: str,
        *,
        scorer_specs: list[ScorerSpec],
        baseline_run_id: str | None = None,
    ) -> EvalRunRecord:
        body: dict[str, Any] = {"scorer_specs": scorer_specs}
        if baseline_run_id is not None:
            body["baseline_run_id"] = baseline_run_id
        res = self._http.post(f"/v1/eval-runs/{eval_run_id}/experiment", body)
        return res["eval_run"]

    def compare(self, eval_run_id: str, *, baseline_run_id: str) -> CompareResponse:
        return self._http.get(
            with_query(f"/v1/eval-runs/{eval_run_id}/compare", baseline=baseline_run_id)
        )


class SuitesResource:
    def __init__(self, http: HttpClient) -> None:
        self._http = http

    def create(
        self,
        *,
        name: str,
        target_type: EvalTargetType,
        description: str | None = None,
        dataset_id: str | None = None,
        scorer_ids: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> EvalSuiteRecord:
        body: dict[str, Any] = {"name": name, "target_type": target_type}
        if description is not None:
            body["description"] = description
        if dataset_id is not None:
            body["dataset_id"] = dataset_id
        if scorer_ids is not None:
            body["scorer_ids"] = scorer_ids
        if metadata is not None:
            body["metadata"] = metadata
        res = self._http.post("/v1/eval-suites", body)
        return res["suite"]

    def list(
        self,
        *,
        limit: int | None = None,
        cursor: str | None = None,
    ) -> EvalSuiteList:
        return self._http.get(with_query("/v1/eval-suites", limit=limit, cursor=cursor))

    def get(self, suite_id: str) -> EvalSuiteRecord:
        res = self._http.get(f"/v1/eval-suites/{suite_id}")
        return res["suite"]

    def run(
        self,
        suite_id: str,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> EvalRunRecord:
        body: dict[str, Any] = {}
        if metadata is not None:
            body["metadata"] = metadata
        res = self._http.post(f"/v1/eval-suites/{suite_id}/run", body)
        return res["eval_run"]


class CasesResource:
    def __init__(self, http: HttpClient) -> None:
        self._http = http

    def create(
        self,
        suite_id: str,
        *,
        name: str,
        dataset_example_id: str | None = None,
        source_run_id: str | None = None,
        source_finding_id: str | None = None,
        source_graph_ref: str | None = None,
        input_bundle: dict[str, Any] | None = None,
        mutations: list[dict[str, Any]] | None = None,
        expected: dict[str, Any] | None = None,
        assertions: list[dict[str, Any]] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> EvalCase:
        body: dict[str, Any] = {"name": name}
        if dataset_example_id is not None:
            body["dataset_example_id"] = dataset_example_id
        if source_run_id is not None:
            body["source_run_id"] = source_run_id
        if source_finding_id is not None:
            body["source_finding_id"] = source_finding_id
        if source_graph_ref is not None:
            body["source_graph_ref"] = source_graph_ref
        if input_bundle is not None:
            body["input_bundle"] = input_bundle
        if mutations is not None:
            body["mutations"] = mutations
        if expected is not None:
            body["expected"] = expected
        if assertions is not None:
            body["assertions"] = assertions
        if metadata is not None:
            body["metadata"] = metadata
        res = self._http.post(f"/v1/eval-suites/{suite_id}/cases", body)
        return res["case"]

    def create_from_run(
        self,
        suite_id: str,
        *,
        source_run_id: str,
        name: str | None = None,
        source_finding_id: str | None = None,
        source_signal_id: str | None = None,
        mutations: list[dict[str, Any]] | None = None,
        expected: dict[str, Any] | None = None,
        assertions: list[dict[str, Any]] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> EvalCase:
        body: dict[str, Any] = {"source_run_id": source_run_id}
        if name is not None:
            body["name"] = name
        if source_finding_id is not None:
            body["source_finding_id"] = source_finding_id
        if source_signal_id is not None:
            body["source_signal_id"] = source_signal_id
        if mutations is not None:
            body["mutations"] = mutations
        if expected is not None:
            body["expected"] = expected
        if assertions is not None:
            body["assertions"] = assertions
        if metadata is not None:
            body["metadata"] = metadata
        res = self._http.post(f"/v1/eval-suites/{suite_id}/cases/from-run", body)
        return res["case"]

    def list(
        self,
        suite_id: str,
        *,
        limit: int | None = None,
        cursor: str | None = None,
    ) -> EvalCaseList:
        return self._http.get(
            with_query(f"/v1/eval-suites/{suite_id}/cases", limit=limit, cursor=cursor)
        )


class EvalRunsResource:
    def __init__(self, http: HttpClient) -> None:
        self._http = http

    def get(self, eval_run_id: str) -> EvalRunRecord:
        res = self._http.get(f"/v1/eval-runs/{eval_run_id}")
        return res["eval_run"]

    def list_results(
        self,
        eval_run_id: str,
        *,
        limit: int | None = None,
        cursor: str | None = None,
    ) -> EvalResultRowList:
        return self._http.get(
            with_query(f"/v1/eval-runs/{eval_run_id}/results", limit=limit, cursor=cursor)
        )


class EvalsResource:
    def __init__(self, http: HttpClient, runs: RunsResource) -> None:
        self._http = http
        self._runs = runs
        self._monitors = MonitorsResource(http)
        self.datasets = DatasetsResource(http)
        self.scorers = ScorersResource(http)
        self.suites = SuitesResource(http)
        self.cases = CasesResource(http)
        self.eval_runs = EvalRunsResource(http)
        self.experiments = ExperimentsResource(http)

    def seed_suite(
        self,
        *,
        name: str,
        rows: list[SeedEvalSuiteRow],
        suite_name: str | None = None,
        description: str | None = None,
        target_type: EvalTargetType = "custom",
        metadata: dict[str, Any] | None = None,
        run: bool = False,
    ) -> SeedEvalSuiteResult:
        """Create a dataset, linked suite, cases, and optionally start the suite."""
        if not rows:
            raise ValueError("seed_suite requires at least one row")
        if suite_name is None or suite_name == name:
            seeded: SeedEvalSuiteResult = self._http.post(
                "/v1/eval-datasets/seed-suite",
                json={
                    "name": name,
                    "description": description,
                    "target_type": target_type,
                    "dataset_metadata": metadata,
                    "suite_metadata": metadata,
                    "rows": [
                        {
                            "name": row.get("name") or f"case-{i:03d}",
                            "input": row["input"],
                            "expected": row.get("expected"),
                            "assertions": row.get("assertions"),
                            "mutations": row.get("mutations"),
                            "metadata": row.get("metadata"),
                        }
                        for i, row in enumerate(rows, start=1)
                    ],
                    "run": run,
                },
            )
            seeded["id"] = seeded["suite"]["id"]
            seeded["dataset_id"] = seeded["dataset"]["id"]
            seeded["suite_id"] = seeded["suite"]["id"]
            seeded["case_count"] = len(seeded.get("cases", []))
            return seeded
        dataset = self.datasets.create(name=name, description=description, metadata=metadata)
        suite = self.suites.create(
            name=suite_name or name,
            description=description,
            target_type=target_type,
            dataset_id=dataset["id"],
            metadata=metadata,
        )
        examples: list[EvalDatasetExample] = []
        cases: list[EvalCase] = []
        for i, row in enumerate(rows, start=1):
            example = self.datasets.append_example(
                dataset["id"],
                input=row["input"],
                expected=row.get("expected"),
                metadata=row.get("metadata"),
            )
            examples.append(example)
            cases.append(
                self.cases.create(
                    suite["id"],
                    name=row.get("name") or f"case-{i:03d}",
                    dataset_example_id=example["id"],
                    input_bundle=row["input"],
                    expected=row.get("expected"),
                    assertions=row.get("assertions"),
                    mutations=row.get("mutations"),
                    metadata=row.get("metadata"),
                )
            )
        result: SeedEvalSuiteResult = {
            "dataset": dataset,
            "suite": suite,
            "examples": examples,
            "cases": cases,
            "id": suite["id"],
            "dataset_id": dataset["id"],
            "suite_id": suite["id"],
            "case_count": len(cases),
        }
        if run:
            result["eval_run"] = self.suites.run(suite["id"])
        return result

    def run_case(
        self,
        *,
        suite: str,
        case: str,
        handler: Callable[[Run], None],
        expected: Any = None,
        inputs: Any = None,
        tags: list[str] | None = None,
        monitor_ids: list[str] | None = None,
        name: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> EvalResult:
        eval_meta: dict[str, Any] = {"suite": suite, "case": case}
        if expected is not None:
            eval_meta["expected"] = expected
        if inputs is not None:
            eval_meta["inputs"] = inputs
        if tags is not None:
            eval_meta["tags"] = tags
        merged_metadata = {**(metadata or {}), "eval": eval_meta}
        run_name = name if name is not None else f"eval:{suite}:{case}"

        run = self._runs.start(name=run_name, metadata=merged_metadata)
        run_id = run.run_id
        try:
            handler(run)
            finished = run.finish()
            run_id = finished["id"]
        except Exception as err:
            try:
                run.fail(str(err))
            except Exception:
                pass
            raise

        if monitor_ids:
            for mid in monitor_ids:
                self._monitors.evaluate(mid, run_id=run_id)

        findings = self._findings_for_run(run_id)
        return {
            "run_id": run_id,
            "suite": suite,
            "case": case,
            "status": derive_status(findings),
            "findings": findings,
        }

    def list_cases(
        self,
        *,
        suite: str,
        limit: int | None = None,
        cursor: str | None = None,
    ) -> EvalListResponse:
        path = with_query("/v1/runs", eval_suite=suite, limit=limit, cursor=cursor)
        res = self._http.get(path)
        records: list[EvalCaseRecord] = []
        for run in res.get("data", []):
            meta = read_eval_metadata(run.get("metadata"))
            if meta is None:
                continue
            findings = self._findings_for_run(run["id"])
            records.append(
                {
                    "run_id": run["id"],
                    "case": meta["case"],
                    "status": derive_status(findings),
                    "created_at": run["created_at"],
                }
            )
        return {"suite": suite, "runs": records, "next_cursor": res.get("next_cursor")}

    def summarize(self, suite: str) -> EvalSummary:
        cursor: str | None = None
        passed = 0
        failed = 0
        for _ in range(20):
            res = self.list_cases(suite=suite, limit=100, cursor=cursor)
            for r in res["runs"]:
                if r["status"] == "pass":
                    passed += 1
                else:
                    failed += 1
            next_cursor = res.get("next_cursor")
            if not next_cursor:
                break
            cursor = next_cursor
        return {"suite": suite, "total": passed + failed, "passed": passed, "failed": failed}

    def _findings_for_run(self, run_id: str) -> list[Finding]:
        path = with_query("/v1/findings", run_id=run_id, limit=100)
        res = self._http.get(path)
        return res.get("data", [])
