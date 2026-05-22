"""Cortex jobs resource: governed launcher, evals, counterfactuals, and the
read-only ``complex_query`` analyst.

Wraps ``POST /v1/cortex/jobs/launch`` and friends. The governed launcher
(:meth:`CortexJobsResource.launch`) runs jobs ``sync`` (block + return the
parsed result) or ``async`` (enqueue + poll :meth:`wait_for_result`). The
ergonomic :meth:`CortexResource.ask` wraps a synchronous ``complex_query``.
"""

from __future__ import annotations

import time
from typing import Any
from urllib.parse import quote

from ._query import with_query
from ._types import (
    CORTEX_TERMINAL_STATUSES,
    ComplexQueryResult,
    CortexJob,
    CortexJobKind,
    CortexJobResult,
    CortexLaunchMode,
    CortexTargetType,
    CreateCortexJobResponse,
    LaunchCortexJobResponse,
    ListCortexJobRunsResponse,
    RetryCortexJobResponse,
)
from .client import HttpClient


class CortexJobsResource:
    def __init__(self, http: HttpClient) -> None:
        self._http = http

    def launch(
        self,
        *,
        project_id: str,
        job_kind: CortexJobKind,
        target_type: CortexTargetType,
        target_ref: str,
        mode: CortexLaunchMode,
        question: str | None = None,
        criteria: dict[str, Any] | None = None,
        input_refs: dict[str, Any] | None = None,
        input_payload: dict[str, Any] | None = None,
        options: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> LaunchCortexJobResponse:
        """Launch a Cortex job through the governed launcher.

        With ``mode="sync"`` the call blocks and returns the parsed ``result``;
        with ``mode="async"`` it enqueues and returns the queued job — poll
        :meth:`wait_for_result`. This is the path the ``complex_query`` analyst
        requires; prefer it over :meth:`create` for new code.
        """
        payload: dict[str, Any] = {
            "project_id": project_id,
            "job_kind": job_kind,
            "target_type": target_type,
            "target_ref": target_ref,
            "mode": mode,
        }
        if question is not None:
            payload["question"] = question
        if criteria is not None:
            payload["criteria"] = criteria
        if input_refs is not None:
            payload["input_refs"] = input_refs
        if input_payload is not None:
            payload["input_payload"] = input_payload
        if options is not None:
            payload["options"] = options
        if idempotency_key is not None:
            payload["idempotency_key"] = idempotency_key
        return self._http.post("/v1/cortex/jobs/launch", json=payload)

    def create(
        self,
        *,
        project_id: str,
        job_kind: CortexJobKind,
        target_type: CortexTargetType,
        target_ref: str,
        question: str | None = None,
        criteria: dict[str, Any] | None = None,
        input_refs: dict[str, Any] | None = None,
        input_payload: dict[str, Any] | None = None,
        options: dict[str, Any] | None = None,
    ) -> CreateCortexJobResponse:
        """Enqueue a Cortex job. Returns ``{job_id, status}`` immediately.

        .. deprecated::
            Prefer :meth:`launch` (the governed launcher).
        """
        payload: dict[str, Any] = {
            "project_id": project_id,
            "job_kind": job_kind,
            "target_type": target_type,
            "target_ref": target_ref,
        }
        if question is not None:
            payload["question"] = question
        if criteria is not None:
            payload["criteria"] = criteria
        if input_refs is not None:
            payload["input_refs"] = input_refs
        if input_payload is not None:
            payload["input_payload"] = input_payload
        if options is not None:
            payload["options"] = options
        return self._http.post("/v1/cortex/jobs", json=payload)

    def list(
        self,
        *,
        status: str | None = None,
        kind: CortexJobKind | None = None,
        cursor: str | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        """List jobs, newest first. Filter by ``status``/``kind``.

        Output: ``{data: [CortexJob], next_cursor}``.
        """
        return self._http.get(
            with_query(
                "/v1/cortex/jobs",
                status=status,
                kind=kind,
                cursor=cursor,
                limit=limit,
            )
        )

    def retry(self, job_id: str) -> RetryCortexJobResponse:
        """Re-queue a failed/dead job for one more attempt."""
        return self._http.post(f"/v1/cortex/jobs/{quote(job_id, safe='')}/retry")

    def runs(self, job_id: str) -> ListCortexJobRunsResponse:
        """List the attempt history (audit-trail runs) for a job."""
        return self._http.get(f"/v1/cortex/jobs/{quote(job_id, safe='')}/runs")

    def get(self, job_id: str) -> CortexJob:
        """Fetch job lifecycle/status without the result body."""
        res = self._http.get(f"/v1/cortex/jobs/{quote(job_id, safe='')}")
        if isinstance(res, dict) and isinstance(res.get("job"), dict):
            return res["job"]
        return res

    def result(self, job_id: str) -> CortexJobResult:
        """Fetch the structured result.

        ``result`` key is absent while the job is still queued/running —
        callers should branch on ``status``.
        """
        return self._http.get(f"/v1/cortex/jobs/{quote(job_id, safe='')}/result")

    def wait_for_result(
        self,
        job_id: str,
        *,
        interval: float = 2.0,
        timeout: float = 120.0,
    ) -> CortexJobResult:
        """Poll :meth:`result` until the job reaches a terminal status.

        Raises ``TimeoutError`` if ``timeout`` seconds elapse first.
        """
        deadline = time.monotonic() + timeout
        while True:
            res = self.result(job_id)
            if res.get("status") in CORTEX_TERMINAL_STATUSES:
                return res
            if time.monotonic() + interval >= deadline:
                raise TimeoutError(
                    f"Cortex job {job_id} did not finish within {timeout}s "
                    f"(last status: {res.get('status')})"
                )
            time.sleep(interval)


class CortexResource:
    """Container exposed as ``client.cortex``."""

    def __init__(self, http: HttpClient) -> None:
        self.jobs = CortexJobsResource(http)

    def ask(
        self,
        question: str,
        *,
        project_id: str,
        target_type: CortexTargetType = "project",
        target_ref: str | None = None,
        mode: CortexLaunchMode = "sync",
        criteria: dict[str, Any] | None = None,
        input_refs: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
        poll_interval: float = 2.0,
        timeout: float = 120.0,
    ) -> ComplexQueryResult:
        """Ask the read-only ``complex_query`` analyst a question; get a cited answer.

        Launches a governed job and returns the parsed
        :class:`ComplexQueryResult`. Defaults to a project-wide, synchronous
        question. Pass ``target_type``/``target_ref`` to anchor on a specific
        run, case, agent, etc., or ``mode="async"`` to enqueue and poll. Raises
        if the job fails or returns a non-``complex_query`` result.

        Note: the analyst executes only when the platform's
        ``CORTEX_TOOL_RUNTIME_ENABLED`` flag is on; otherwise the job is skipped.
        """
        ref = target_ref
        if ref is None and target_type == "project":
            ref = project_id
        if ref is None:
            raise ValueError(
                f"cortex.ask: target_ref is required for target_type '{target_type}'"
            )

        launched = self.jobs.launch(
            project_id=project_id,
            job_kind="complex_query",
            target_type=target_type,
            target_ref=ref,
            mode=mode,
            question=question,
            criteria=criteria,
            input_refs=input_refs,
            idempotency_key=idempotency_key,
        )

        status = launched.get("status")
        result = launched.get("result")
        error = launched.get("error")

        # A sync launch returns a terminal status with the result/error embedded;
        # only poll when the job is still in flight (async, or a non-terminal sync).
        if status not in CORTEX_TERMINAL_STATUSES:
            polled = self.jobs.wait_for_result(
                launched["job_id"], interval=poll_interval, timeout=timeout
            )
            status = polled.get("status")
            result = polled.get("result")
            error = polled.get("error")

        if status != "succeeded" or result is None:
            suffix = f": {error}" if error else ""
            raise RuntimeError(
                f"cortex.ask: job {launched['job_id']} {status}{suffix}"
            )
        if result.get("kind") != "complex_query":
            raise RuntimeError(
                f"cortex.ask: expected complex_query result, got '{result.get('kind')}'"
            )
        return result  # type: ignore[return-value]
