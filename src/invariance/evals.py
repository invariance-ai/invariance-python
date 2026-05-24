"""Evals — record eval suites/cases as runs and derive pass/fail from findings.

Mirrors the TypeScript SDK's ``inv.evals`` resource. An eval case = a run
tagged with ``metadata.eval = {suite, case, ...}``. Status is derived from
findings of severity >= medium that are still open.
"""

from __future__ import annotations

from typing import Any, Callable, Literal, TypedDict

from ._query import with_query
from ._types import Finding, Severity
from .client import HttpClient
from .findings import FindingsResource
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


EvalStatus = Literal["pass", "fail"]


class EvalMetadata(TypedDict, total=False):
    suite: str
    case: str
    expected: Any
    inputs: Any
    tags: list[str]


class EvalResult(TypedDict):
    run_id: str
    suite: str
    case: str
    status: EvalStatus
    findings: list[Finding]


class EvalCaseRecord(TypedDict):
    run_id: str
    case: str
    status: EvalStatus
    created_at: str


class EvalListResponse(TypedDict):
    suite: str
    runs: list[EvalCaseRecord]
    next_cursor: str | None


class EvalSummary(TypedDict):
    suite: str
    total: int
    passed: int
    failed: int


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
        out["tags"] = tags
    return out


def derive_status(findings: list[Finding]) -> EvalStatus:
    threshold = _SEVERITY_ORDER[_FAIL_THRESHOLD]
    for f in findings:
        status = f.get("status")
        if status not in ("open", "review_requested"):
            continue
        sev = f.get("severity")
        if sev is None:
            continue
        if _SEVERITY_ORDER.get(sev, 0) >= threshold:
            return "fail"
    return "pass"


class EvalsResource:
    def __init__(self, http: HttpClient, runs: RunsResource) -> None:
        self._http = http
        self._runs = runs
        self._monitors = MonitorsResource(http)
        self._findings = FindingsResource(http)

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
        md = {**(metadata or {}), "eval": eval_meta}
        run_name = name if name is not None else f"eval:{suite}:{case}"

        run = self._runs.start(name=run_name, metadata=md)
        run_id: str
        with run as r:
            run_id = r.run_id
            handler(r)
        # context manager finishes on clean exit; on exception, marks failed and re-raises.

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
        path = with_query(
            "/v1/runs",
            eval_suite=suite,
            limit=limit,
            cursor=cursor,
        )
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
        return {
            "suite": suite,
            "runs": records,
            "next_cursor": res.get("next_cursor"),
        }

    def summarize(self, suite: str) -> EvalSummary:
        cursor: str | None = None
        passed = 0
        failed = 0
        for _ in range(20):
            res = self.list_cases(suite=suite, cursor=cursor, limit=100)
            for r in res["runs"]:
                if r["status"] == "pass":
                    passed += 1
                else:
                    failed += 1
            nc = res.get("next_cursor")
            if not nc:
                break
            cursor = nc
        return {"suite": suite, "total": passed + failed, "passed": passed, "failed": failed}

    def _findings_for_run(self, run_id: str) -> list[Finding]:
        res = self._http.get(with_query("/v1/findings", run_id=run_id, limit=100))
        return list(res.get("data", []))
