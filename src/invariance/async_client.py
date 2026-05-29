"""Async mirror of Invariance, Run, Step, and @trace.

Mirrors the sync surface: ``async with inv.runs.start() as run:`` and
``async with run.step(...) as s:``. Uses :class:`asyncio.Lock` per run to
serialize writes so two concurrent tasks inside the same run cannot
produce a branched chain (the backend has no conflict detection).
"""

from __future__ import annotations

import asyncio
import contextvars
import functools
import inspect
import traceback
import uuid
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Callable, TypeVar

import httpx

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
    Agent,
    AgentList,
    AskContentBlock,
    AskResponse,
    AskRole,
    BuiltinScorerList,
    CompareResponse,
    CreateAgentResponse,
    AgentUsage,
    DashboardViz,
    Divergence,
    DivergenceKind,
    DivergenceList,
    DivergenceStatus,
    ExternalReceipt,
    ExternalReceiptList,
    ExternalReceiptSource,
    Guardrail,
    GuardrailList,
    GuardrailMode,
    GuardrailStatus,
    OverviewMetrics,
    QueryResult,
    QuerySource,
    QuerySpec,
    Recipe,
    RecipeList,
    SavedView,
    SavedViewList,
    SavedViewVisibility,
    WorkflowEventActorType,
    WorkflowEventList,
    WorkflowExecutionHealthList,
    WorkflowObservabilityRollup,
    WorkflowObservabilityRollupList,
    EvalCase,
    EvalCaseList,
    EvalCaseRecord,
    EvalDataset,
    EvalDatasetExample,
    EvalDatasetExampleList,
    EvalDatasetList,
    EvalListResponse,
    EvalResult,
    EvalResultRowList,
    EvalRunRecord,
    EvalScorer,
    EvalScorerKind,
    EvalScorerList,
    EvalSuiteList,
    EvalSuiteRecord,
    EvalSummary,
    EvalTargetType,
    EvaluateMonitorResponse,
    EvidenceRef,
    Finding,
    FindingList,
    FindingStatus,
    GetMeResponse,
    KbMessage,
    KbPage,
    KbPageKind,
    KbPageList,
    KbSession,
    KbSessionList,
    MemoryReadResponse,
    MemorySource,
    MemorySubjectType,
    MemoryWriteResponse,
    Monitor,
    MonitorExecutionList,
    MonitorList,
    Narrative,
    Node,
    NodeList,
    OperationalGraphResponse,
    Review,
    ReviewDecision,
    ReviewList,
    ReviewResponse,
    RunList,
    RunInspection,
    RunProof,
    ScorerSpec,
    SeedEvalSuiteResult,
    SeedEvalSuiteRow,
    Severity,
    Signal,
    SignalList,
)
from .cases import _CaseContext, _current_case
from .receipts import _build_receipt_body
from .evals import derive_status, read_eval_metadata
from .memory import _build_read_body as _build_memory_read_body
from .memory import _build_write_body as _build_memory_write_body
from .client import InvarianceApiError, RateLimitError
from .config import resolve_config
from ._retry import RetryPolicy, backoff_delay, parse_retry_after, should_retry
from .monitors import MonitorSpec, compile_monitor
from ._internal import build_node_body, now_ms as _now_ms, random_node_id as _random_node_id
from ._query import with_query
from .handoff_token import HandoffToken, build_handoff_token
from .observability import summarize_run_observability

DEFAULT_API_URL = "https://api.useinvariance.com"
BATCH_MAX = 100


_current_async_step: contextvars.ContextVar["AsyncStep | None"] = contextvars.ContextVar(
    "invariance_current_async_step", default=None
)


class AsyncHttpClient:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        retry_policy: RetryPolicy | None = None,
    ) -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=30.0,
        )
        self._retry = retry_policy or RetryPolicy()

    async def request(
        self,
        method: str,
        path: str,
        *,
        json: Any | None = None,
        idempotency_key: str | None = None,
    ) -> Any:
        headers: dict[str, str] | None = None
        if method.upper() not in ("GET", "HEAD", "OPTIONS"):
            headers = {"Idempotency-Key": idempotency_key or uuid.uuid4().hex}

        last_status = 0
        for attempt in range(self._retry.max_retries + 1):
            res = await self._client.request(method, path, json=json, headers=headers)
            if res.status_code < 400 or not should_retry(res.status_code):
                break
            last_status = res.status_code
            if attempt >= self._retry.max_retries:
                break
            retry_after = parse_retry_after(res.headers.get("Retry-After"))
            await asyncio.sleep(backoff_delay(self._retry, attempt + 1, retry_after))
        if res.status_code >= 400:
            body: dict[str, Any] = {}
            try:
                body = res.json()
            except Exception:
                pass
            err = body.get("error", {})
            cls = RateLimitError if last_status == 429 else InvarianceApiError
            raise cls(
                status=res.status_code,
                code=err.get("code", "unknown"),
                message=err.get("message", f"HTTP {res.status_code}"),
                details=err.get("details"),
                request_id=err.get("request_id"),
            )
        if res.status_code == 204 or not res.content:
            return None
        return res.json()

    async def get(self, path: str) -> Any:
        return await self.request("GET", path)

    async def post(
        self,
        path: str,
        json: Any | None = None,
        *,
        idempotency_key: str | None = None,
    ) -> Any:
        return await self.request("POST", path, json=json, idempotency_key=idempotency_key)

    async def patch(
        self,
        path: str,
        json: Any | None = None,
        *,
        idempotency_key: str | None = None,
    ) -> Any:
        return await self.request("PATCH", path, json=json, idempotency_key=idempotency_key)

    async def delete(self, path: str, *, idempotency_key: str | None = None) -> Any:
        return await self.request("DELETE", path, idempotency_key=idempotency_key)

    async def aclose(self) -> None:
        await self._client.aclose()


class AsyncStep:
    def __init__(
        self,
        run: "AsyncRun",
        action_type: str,
        *,
        input: Any | None = None,
        output: Any | None = None,
        metadata: dict[str, Any] | None = None,
        custom_fields: dict[str, Any] | None = None,
        type: str | None = None,
        handoff_from: str | None = None,
        handoff_to: str | None = None,
        handoff_reason: str | None = None,
    ) -> None:
        self._run = run
        self.action_type = action_type
        self.type = type
        self.input = input
        self.output = output
        self.error: Any | None = None
        self.metadata = dict(metadata) if metadata else None
        self.custom_fields = dict(custom_fields) if custom_fields else None
        self.handoff_from = handoff_from
        self.handoff_to = handoff_to
        self.handoff_reason = handoff_reason
        self.id = _random_node_id()
        self._parent_id: str | None = None
        self._start_ms: int | None = None
        self._token: contextvars.Token | None = None

    async def __aenter__(self) -> "AsyncStep":
        parent = _current_async_step.get()
        self._parent_id = parent.id if parent is not None else None
        self._start_ms = _now_ms()
        self._token = _current_async_step.set(self)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> bool:
        try:
            if exc_val is not None and self.error is None:
                self.error = {
                    "type": exc_type.__name__ if exc_type else "Exception",
                    "message": str(exc_val),
                    "traceback": "".join(traceback.format_exception(exc_type, exc_val, exc_tb)),
                }
            duration_ms = _now_ms() - (self._start_ms or _now_ms())
            await self._run._emit(
                id=self.id,
                action_type=self.action_type,
                type=self.type,
                input=self.input,
                output=self.output,
                error=self.error,
                metadata=self.metadata,
                custom_fields=self.custom_fields,
                parent_id=self._parent_id,
                timestamp=self._start_ms,
                duration_ms=duration_ms,
                handoff_from=self.handoff_from,
                handoff_to=self.handoff_to,
                handoff_reason=self.handoff_reason,
            )
        finally:
            if self._token is not None:
                _current_async_step.reset(self._token)
                self._token = None
        return False


class AsyncRun:
    def __init__(
        self,
        http: AsyncHttpClient,
        session: dict[str, Any],
        signing_key: str | None = None,
        buffered: bool = True,
    ) -> None:
        self._http = http
        self._session = session
        self._signing_key = signing_key
        self._last_hash: str | None = None
        self._last_node_id: str | None = None
        self._buffered = buffered
        self._buffer: list[dict[str, Any]] = []
        self._lock = asyncio.Lock()
        self._closed = False

    @property
    def run_id(self) -> str:
        return self._session["id"]

    @property
    def name(self) -> str:
        return self._session.get("name", "")

    @property
    def status(self) -> str:
        return self._session.get("status", "open")

    async def __aenter__(self) -> "AsyncRun":
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> bool:
        try:
            await self.flush()
        finally:
            if not self._closed:
                if exc_val is not None:
                    await self.fail(error=str(exc_val))
                else:
                    await self.finish()
        return False

    def step(
        self,
        action_type: str,
        *,
        input: Any | None = None,
        output: Any | None = None,
        metadata: dict[str, Any] | None = None,
        custom_fields: dict[str, Any] | None = None,
        type: str | None = None,
        handoff_from: str | None = None,
        handoff_to: str | None = None,
        handoff_reason: str | None = None,
    ) -> AsyncStep:
        return AsyncStep(
            self,
            action_type,
            input=input,
            output=output,
            metadata=metadata,
            custom_fields=custom_fields,
            type=type,
            handoff_from=handoff_from,
            handoff_to=handoff_to,
            handoff_reason=handoff_reason,
        )

    async def handoff(
        self,
        to_agent_id: str,
        *,
        message: Any | None = None,
        reason: str | None = None,
        from_agent_id: str | None = None,
    ) -> HandoffToken | None:
        """Emit a 'handoff' node marking delegation to another agent.

        Mirrors :meth:`invariance.runs.Run.handoff`. Returns a signed
        :class:`HandoffToken` when the run is signed; ``None`` otherwise.
        """
        issuer_agent_id = from_agent_id or self._session.get("agent_id")
        async with self.step(
            "handoff",
            type="handoff",
            input={"message": message} if message is not None else None,
            handoff_from=issuer_agent_id,
            handoff_to=to_agent_id,
            handoff_reason=reason,
        ):
            pass
        if not self._signing_key or self._last_hash is None or self._last_node_id is None:
            return None
        await self.flush()
        return build_handoff_token(
            iss_agent_id=issuer_agent_id,
            iss_run_id=self.run_id,
            handoff_node_id=self._last_node_id,
            handoff_node_hash=self._last_hash,
            to_agent_id=to_agent_id,
            signing_key=self._signing_key,
            iat_ms=_now_ms(),
        )

    async def _emit(
        self,
        *,
        id: str,
        action_type: str,
        type: str | None,
        input: Any | None,
        output: Any | None,
        error: Any | None,
        metadata: dict[str, Any] | None,
        custom_fields: dict[str, Any] | None,
        parent_id: str | None,
        timestamp: int | None,
        duration_ms: int | None,
        handoff_from: str | None = None,
        handoff_to: str | None = None,
        handoff_reason: str | None = None,
    ) -> None:
        async with self._lock:
            body, self._last_hash = build_node_body(
                run_id=self.run_id,
                agent_id=self._session["agent_id"],
                last_hash=self._last_hash,
                signing_key=self._signing_key,
                id=id,
                action_type=action_type,
                type=type,
                handoff_from=handoff_from,
                handoff_to=handoff_to,
                handoff_reason=handoff_reason,
                input=input,
                output=output,
                error=error,
                metadata=metadata,
                custom_fields=custom_fields,
                parent_id=parent_id,
                timestamp=timestamp,
                duration_ms=duration_ms,
            )
            self._buffer.append(body)
            self._last_node_id = body["id"]
            if not self._buffered or len(self._buffer) >= BATCH_MAX:
                await self._flush_locked()

    async def flush(self) -> None:
        async with self._lock:
            await self._flush_locked()

    async def _flush_locked(self) -> None:
        while self._buffer:
            chunk = self._buffer[:BATCH_MAX]
            self._buffer = self._buffer[BATCH_MAX:]
            res = await self._http.post("/v1/nodes", json=chunk)
            nodes = res["data"]
            if nodes:
                last = nodes[-1]
                if "hash" in last and not self._signing_key:
                    self._last_hash = last["hash"]

    async def signal(
        self,
        spec: dict[str, Any] | None = None,
        *,
        severity: Severity | None = None,
        title: str | None = None,
        message: str | None = None,
        type: str | None = None,
        data: Any | None = None,
        node_id: str | None = None,
        run_id: str | None = None,
    ) -> dict[str, Any]:
        """Async mirror of :meth:`Run.signal`."""
        await self.flush()
        merged: dict[str, Any] = dict(spec) if spec else {}
        if severity is not None:
            merged["severity"] = severity
        if title is not None:
            merged["title"] = title
        if message is not None:
            merged["message"] = message
        if type is not None:
            merged["type"] = type
        if data is not None:
            merged["data"] = data
        if node_id is not None:
            merged["node_id"] = node_id
        if run_id is not None:
            merged["run_id"] = run_id
        if "severity" not in merged or "title" not in merged:
            raise ValueError("signal() requires severity and title (directly or via spec)")
        merged.setdefault("run_id", self.run_id)
        if "node_id" not in merged and self._last_node_id is not None:
            merged["node_id"] = self._last_node_id

        body: dict[str, Any] = {"severity": merged["severity"], "title": merged["title"]}
        for key in ("message", "type", "data", "node_id", "run_id"):
            if key in merged:
                body[key] = merged[key]
        res = await self._http.post("/v1/signals", json=body)
        return res["signal"]

    async def verify(self) -> RunProof:
        return await self._http.get(f"/v1/runs/{self.run_id}/verify")

    async def finish(self) -> dict[str, Any]:
        await self.flush()
        res = await self._http.patch(f"/v1/runs/{self.run_id}", json={"status": "completed"})
        self._closed = True
        return res["run"]

    async def fail(self, error: str | None = None) -> dict[str, Any]:
        await self.flush()
        body: dict[str, Any] = {"status": "failed"}
        if error:
            body["metadata"] = {"error": error}
        res = await self._http.patch(f"/v1/runs/{self.run_id}", json=body)
        self._closed = True
        return res["run"]


class AsyncRunsResource:
    def __init__(self, http: AsyncHttpClient, signing_key: str | None = None) -> None:
        self._http = http
        self._signing_key = signing_key

    async def start(
        self,
        name: str | None = None,
        metadata: dict[str, Any] | None = None,
        *,
        signing_key: str | None = None,
        buffered: bool = True,
    ) -> AsyncRun:
        body: dict[str, Any] = {}
        if name is not None:
            body["name"] = name
        if metadata is not None:
            body["metadata"] = metadata
        res = await self._http.post("/v1/runs", json=body)
        return AsyncRun(self._http, res["run"], signing_key or self._signing_key, buffered=buffered)

    async def list(self, *, cursor: str | None = None, limit: int | None = None) -> RunList:
        return await self._http.get(with_query("/v1/runs", cursor=cursor, limit=limit))

    async def get(self, id: str) -> AsyncRun:
        res = await self._http.get(f"/v1/runs/{id}")
        return AsyncRun(self._http, res["run"], self._signing_key)

    async def inspect(
        self,
        run_id: str,
        *,
        limit: int = 200,
        include_operational_graph: bool = True,
    ) -> RunInspection:
        """Fetch an agent-readable inspection bundle for a run."""
        run_res, nodes_page = await asyncio.gather(
            self._http.get(f"/v1/runs/{run_id}"),
            self._http.get(with_query(f"/v1/runs/{run_id}/nodes", limit=limit)),
        )
        graph = None
        if include_operational_graph:
            try:
                graph = await self.operational_graph(run_id)
            except Exception:
                graph = None
        nodes = nodes_page.get("data", [])
        return {
            "run": run_res["run"],
            "nodes": nodes,
            "observability": summarize_run_observability(run_id, nodes),
            "operational_graph": graph,
        }

    async def operational_graph(self, run_id: str) -> OperationalGraphResponse:
        """Fetch the operational graph for a run — entities, edges, findings,
        and a completeness score (MVP spec §4)."""
        return await self._http.get(f"/v1/runs/{run_id}/operational-graph")


class AsyncNodesResource:
    def __init__(self, http: AsyncHttpClient) -> None:
        self._http = http

    async def write(
        self,
        run_id: str,
        nodes: list[dict[str, Any]],
    ) -> list[Node]:
        body = [{"run_id": run_id, **n} for n in nodes]
        res = await self._http.post("/v1/nodes", json=body)
        return res["data"]

    async def list(
        self,
        run_id: str,
        *,
        cursor: str | None = None,
        limit: int | None = None,
    ) -> NodeList:
        return await self._http.get(
            with_query(f"/v1/runs/{run_id}/nodes", cursor=cursor, limit=limit)
        )


class AsyncAgentsResource:
    def __init__(self, http: AsyncHttpClient) -> None:
        self._http = http

    async def me(self) -> GetMeResponse:
        return await self._http.get("/v1/agents/me")

    async def set_public_key(self, public_key: str) -> Agent:
        res = await self._http.request(
            "PUT", "/v1/agents/me/key", json={"public_key": public_key}
        )
        return res["agent"]

    async def create(
        self,
        *,
        name: str,
        project_id: str,
        public_key: str | None = None,
        key_mode: str | None = None,
    ) -> CreateAgentResponse:
        body: dict[str, Any] = {"name": name, "project_id": project_id}
        if public_key is not None:
            body["public_key"] = public_key
        if key_mode is not None:
            body["key_mode"] = key_mode
        return await self._http.post("/v1/agents", json=body)

    async def list(self, *, project_id: str) -> AgentList:
        return await self._http.get(with_query("/v1/agents", project_id=project_id))

    async def get(self, id: str) -> Agent:
        res = await self._http.get(f"/v1/agents/{id}")
        return res["agent"]


class AsyncMonitorsResource:
    def __init__(self, http: AsyncHttpClient) -> None:
        self._http = http

    async def create(self, spec: MonitorSpec) -> Monitor:
        res = await self._http.post("/v1/monitors", json=compile_monitor(spec))
        return res["monitor"]

    async def get(self, id: str) -> Monitor:
        res = await self._http.get(f"/v1/monitors/{id}")
        return res["monitor"]

    async def list(
        self,
        *,
        cursor: str | None = None,
        limit: int | None = None,
    ) -> MonitorList:
        return await self._http.get(with_query("/v1/monitors", cursor=cursor, limit=limit))

    async def update(
        self,
        id: str,
        *,
        name: str | None = None,
        description: str | None = None,
        enabled: bool | None = None,
        mode: str | None = None,
        evaluator: dict[str, Any] | None = None,
        schedule: dict[str, Any] | None = None,
        creates_review: bool | None = None,
        signal_type: str | None = None,
    ) -> Monitor:
        patch: dict[str, Any] = {}
        if name is not None:
            patch["name"] = name
        if description is not None:
            patch["description"] = description
        if enabled is not None:
            patch["enabled"] = enabled
        if mode is not None:
            patch["mode"] = mode
        if evaluator is not None:
            patch["evaluator"] = evaluator
        if schedule is not None:
            patch["schedule"] = schedule
        if creates_review is not None:
            patch["creates_review"] = creates_review
        if signal_type is not None:
            patch["signal_type"] = signal_type
        res = await self._http.patch(f"/v1/monitors/{id}", json=patch)
        return res["monitor"]

    async def pause(self, id: str) -> Monitor:
        return await self.update(id, enabled=False)

    async def resume(self, id: str) -> Monitor:
        return await self.update(id, enabled=True)

    async def delete(self, id: str) -> None:
        await self._http.delete(f"/v1/monitors/{id}")

    async def evaluate(
        self,
        id: str,
        *,
        run_id: str | None = None,
        since: str | None = None,
        limit: int | None = None,
    ) -> EvaluateMonitorResponse:
        body: dict[str, Any] = {}
        if run_id is not None:
            body["run_id"] = run_id
        if since is not None:
            body["since"] = since
        if limit is not None:
            body["limit"] = limit
        return await self._http.post(f"/v1/monitors/{id}/evaluate", json=body)

    async def preview_target(
        self,
        *,
        target: dict[str, Any] | None = None,
        monitor_id: str | None = None,
        sample_limit: int | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {}
        if target is not None:
            body["target"] = target
        if monitor_id is not None:
            body["monitor_id"] = monitor_id
        if sample_limit is not None:
            body["sample_limit"] = sample_limit
        return await self._http.post("/v1/monitors/preview-target", json=body)

    async def preview_evaluator(
        self,
        *,
        evaluator: dict[str, Any],
        target: dict[str, Any] | None = None,
        sample_limit: int | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"evaluator": evaluator}
        if target is not None:
            body["target"] = target
        if sample_limit is not None:
            body["sample_limit"] = sample_limit
        return await self._http.post("/v1/monitors/preview-evaluator", json=body)

    async def executions(
        self,
        id: str,
        *,
        cursor: str | None = None,
        limit: int | None = None,
    ) -> MonitorExecutionList:
        return await self._http.get(
            with_query(f"/v1/monitors/{id}/executions", cursor=cursor, limit=limit)
        )

    async def findings(
        self,
        id: str,
        *,
        cursor: str | None = None,
        limit: int | None = None,
    ) -> FindingList:
        return await self._http.get(
            with_query(f"/v1/monitors/{id}/findings", cursor=cursor, limit=limit)
        )


class AsyncMonitorRoutesResource:
    """CRUD + test for monitor delivery routes (webhook / slack_webhook)."""

    def __init__(self, http: AsyncHttpClient) -> None:
        self._http = http

    async def create(
        self,
        *,
        target_type: str,
        config: dict[str, Any],
        events: list[str],
        monitor_id: str | None = None,
        enabled: bool | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"target_type": target_type, "config": config, "events": events}
        if monitor_id is not None:
            body["monitor_id"] = monitor_id
        if enabled is not None:
            body["enabled"] = enabled
        res = await self._http.post("/v1/monitor-routes", json=body)
        return res["route"]

    async def list(
        self,
        *,
        monitor_id: str | None = None,
        cursor: str | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        return await self._http.get(
            with_query("/v1/monitor-routes", monitor_id=monitor_id, cursor=cursor, limit=limit)
        )

    async def get(self, id: str) -> dict[str, Any]:
        res = await self._http.get(f"/v1/monitor-routes/{id}")
        return res["route"]

    async def update(
        self,
        id: str,
        *,
        target_type: str | None = None,
        config: dict[str, Any] | None = None,
        events: list[str] | None = None,
        monitor_id: str | None = None,
        enabled: bool | None = None,
    ) -> dict[str, Any]:
        patch: dict[str, Any] = {}
        if target_type is not None:
            patch["target_type"] = target_type
        if config is not None:
            patch["config"] = config
        if events is not None:
            patch["events"] = events
        if monitor_id is not None:
            patch["monitor_id"] = monitor_id
        if enabled is not None:
            patch["enabled"] = enabled
        res = await self._http.patch(f"/v1/monitor-routes/{id}", json=patch)
        return res["route"]

    async def delete(self, id: str) -> None:
        await self._http.delete(f"/v1/monitor-routes/{id}")

    async def test(self, id: str) -> dict[str, Any]:
        return await self._http.post(f"/v1/monitor-routes/{id}/test", json={})


class AsyncSignalsResource:
    def __init__(self, http: AsyncHttpClient) -> None:
        self._http = http

    async def emit(
        self,
        *,
        severity: Severity,
        title: str,
        message: str | None = None,
        type: str | None = None,
        data: Any | None = None,
        node_id: str | None = None,
        run_id: str | None = None,
    ) -> Signal:
        body: dict[str, Any] = {"severity": severity, "title": title}
        if message is not None:
            body["message"] = message
        if type is not None:
            body["type"] = type
        if data is not None:
            body["data"] = data
        if node_id is not None:
            body["node_id"] = node_id
        if run_id is not None:
            body["run_id"] = run_id
        res = await self._http.post("/v1/signals", json=body)
        return res["signal"]

    async def list(
        self, *, cursor: str | None = None, limit: int | None = None
    ) -> SignalList:
        return await self._http.get(with_query("/v1/signals", cursor=cursor, limit=limit))

    async def get(self, id: str) -> Signal:
        res = await self._http.get(f"/v1/signals/{id}")
        return res["signal"]

    async def acknowledge(self, id: str) -> Signal:
        res = await self._http.patch(f"/v1/signals/{id}/acknowledge")
        return res["signal"]

    async def resolve(self, id: str) -> Signal:
        res = await self._http.patch(f"/v1/signals/{id}/resolve")
        return res["signal"]


class AsyncProofsResource:
    def __init__(self, http: AsyncHttpClient) -> None:
        self._http = http

    async def verify_run(self, run_id: str) -> RunProof:
        return await self._http.get(f"/v1/runs/{run_id}/verify")


class AsyncFindingsResource:
    def __init__(self, http: AsyncHttpClient) -> None:
        self._http = http

    async def list(
        self,
        *,
        cursor: str | None = None,
        limit: int | None = None,
    ) -> FindingList:
        return await self._http.get(with_query("/v1/findings", cursor=cursor, limit=limit))

    async def get(self, id: str) -> Finding:
        res = await self._http.get(f"/v1/findings/{id}")
        return res["finding"]

    async def update(self, id: str, *, status: FindingStatus) -> Finding:
        res = await self._http.patch(f"/v1/findings/{id}", json={"status": status})
        return res["finding"]


class AsyncReviewsResource:
    def __init__(self, http: AsyncHttpClient) -> None:
        self._http = http

    async def list(
        self,
        *,
        cursor: str | None = None,
        limit: int | None = None,
    ) -> ReviewList:
        return await self._http.get(with_query("/v1/reviews", cursor=cursor, limit=limit))

    async def get(self, id: str) -> Review:
        res = await self._http.get(f"/v1/reviews/{id}")
        return res["review"]

    async def claim(self, id: str, *, notes: str | None = None) -> Review:
        body: dict[str, Any] = {"status": "claimed"}
        if notes is not None:
            body["notes"] = notes
        res = await self._http.patch(f"/v1/reviews/{id}", json=body)
        return res["review"]

    async def unclaim(self, id: str, *, notes: str | None = None) -> Review:
        body: dict[str, Any] = {"status": "pending"}
        if notes is not None:
            body["notes"] = notes
        res = await self._http.patch(f"/v1/reviews/{id}", json=body)
        return res["review"]

    async def resolve(
        self,
        id: str,
        *,
        decision: ReviewDecision,
        notes: str | None = None,
    ) -> ReviewResponse:
        body: dict[str, Any] = {"decision": decision}
        if notes is not None:
            body["notes"] = notes
        return await self._http.patch(f"/v1/reviews/{id}", json=body)


class AsyncNarrativesResource:
    def __init__(self, http: AsyncHttpClient) -> None:
        self._http = http

    async def get(self, run_id: str, *, refresh: bool = False) -> Narrative:
        path = f"/v1/runs/{run_id}/narrative"
        if refresh:
            path += "?refresh=true"
        res = await self._http.get(path)
        return res["narrative"]


class AsyncNodeTypesResource:
    """Async sibling of :class:`invariance.NodeTypesResource`."""

    def __init__(self, http: AsyncHttpClient) -> None:
        self._http = http

    async def list(self) -> list[dict[str, Any]]:
        res = await self._http.get("/v1/node-types")
        return res["data"]

    async def register(
        self,
        name: str,
        *,
        display_name: str | None = None,
        custom_fields_schema: dict[str, Any] | None = None,
        aggregation_hints: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"name": name}
        if display_name is not None:
            body["display_name"] = display_name
        if custom_fields_schema is not None:
            body["custom_fields_schema"] = custom_fields_schema
        if aggregation_hints is not None:
            body["aggregation_hints"] = aggregation_hints
        res = await self._http.post("/v1/node-types", json=body)
        return res["node_type"]


class AsyncKbResource:
    def __init__(self, http: AsyncHttpClient) -> None:
        self._http = http

    async def create_page(
        self,
        *,
        path: str,
        title: str,
        body: str,
        summary: str | None = None,
        kind: KbPageKind | None = None,
    ) -> KbPage:
        payload: dict[str, Any] = {"path": path, "title": title, "body": body}
        if summary is not None:
            payload["summary"] = summary
        if kind is not None:
            payload["kind"] = kind
        res = await self._http.post("/v1/kb/pages", json=payload)
        return res["page"]

    async def list_pages(
        self,
        *,
        kind: KbPageKind | None = None,
        search: str | None = None,
        cursor: str | None = None,
        limit: int | None = None,
    ) -> KbPageList:
        return await self._http.get(
            with_query("/v1/kb/pages", kind=kind, search=search, cursor=cursor, limit=limit)
        )

    async def get_page(self, id: str) -> KbPage:
        res = await self._http.get(f"/v1/kb/pages/{id}")
        return res["page"]

    async def update_page(
        self,
        id: str,
        *,
        title: str | None = None,
        body: str | None = None,
        summary: str | None = None,
        kind: KbPageKind | None = None,
    ) -> KbPage:
        payload: dict[str, Any] = {}
        if title is not None:
            payload["title"] = title
        if body is not None:
            payload["body"] = body
        if summary is not None:
            payload["summary"] = summary
        if kind is not None:
            payload["kind"] = kind
        res = await self._http.patch(f"/v1/kb/pages/{id}", json=payload)
        return res["page"]

    async def delete_page(self, id: str) -> None:
        await self._http.delete(f"/v1/kb/pages/{id}")

    async def create_session(
        self,
        *,
        title: str | None = None,
        model: str | None = None,
    ) -> KbSession:
        payload: dict[str, Any] = {}
        if title is not None:
            payload["title"] = title
        if model is not None:
            payload["model"] = model
        res = await self._http.post("/v1/kb/sessions", json=payload)
        return res["session"]

    async def list_sessions(
        self,
        *,
        cursor: str | None = None,
        limit: int | None = None,
    ) -> KbSessionList:
        return await self._http.get(with_query("/v1/kb/sessions", cursor=cursor, limit=limit))

    async def get_session(self, id: str) -> KbSession:
        res = await self._http.get(f"/v1/kb/sessions/{id}")
        return res["session"]

    async def delete_session(self, id: str) -> None:
        await self._http.delete(f"/v1/kb/sessions/{id}")

    async def list_messages(self, id: str) -> list[KbMessage]:
        res = await self._http.get(f"/v1/kb/sessions/{id}/messages")
        return res["messages"]

    async def append_message(
        self,
        id: str,
        *,
        content: str | list[AskContentBlock],
        role: AskRole | None = None,
    ) -> KbMessage:
        payload: dict[str, Any] = {"content": content}
        if role is not None:
            payload["role"] = role
        res = await self._http.post(f"/v1/kb/sessions/{id}/messages", json=payload)
        return res["message"]


class AsyncAskResource:
    def __init__(self, http: AsyncHttpClient) -> None:
        self._http = http

    async def send(
        self,
        message: str,
        *,
        session_id: str | None = None,
        model: str | None = None,
        max_turns: int | None = None,
    ) -> AskResponse:
        payload: dict[str, Any] = {"message": message}
        if session_id is not None:
            payload["session_id"] = session_id
        if model is not None:
            payload["model"] = model
        if max_turns is not None:
            payload["max_turns"] = max_turns
        return await self._http.post("/v1/ask", json=payload)


class AsyncCortexJobsResource:
    def __init__(self, http: AsyncHttpClient) -> None:
        self._http = http

    async def launch(
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
        """Launch a Cortex job through the governed launcher (sync/async)."""
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
        return await self._http.post("/v1/cortex/jobs/launch", json=payload)

    async def create(
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
        """Enqueue a Cortex job via the legacy endpoint.

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
        return await self._http.post("/v1/cortex/jobs", json=payload)

    async def list(
        self,
        *,
        status: str | None = None,
        kind: CortexJobKind | None = None,
        cursor: str | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        """List jobs, newest first. Output: ``{data, next_cursor}``."""
        return await self._http.get(
            with_query(
                "/v1/cortex/jobs",
                status=status,
                kind=kind,
                cursor=cursor,
                limit=limit,
            )
        )

    async def retry(self, job_id: str) -> RetryCortexJobResponse:
        """Re-queue a failed/dead job for one more attempt."""
        from urllib.parse import quote

        return await self._http.post(
            f"/v1/cortex/jobs/{quote(job_id, safe='')}/retry"
        )

    async def runs(self, job_id: str) -> ListCortexJobRunsResponse:
        """List the attempt history (audit-trail runs) for a job."""
        from urllib.parse import quote

        return await self._http.get(
            f"/v1/cortex/jobs/{quote(job_id, safe='')}/runs"
        )

    async def get(self, job_id: str) -> CortexJob:
        from urllib.parse import quote

        res = await self._http.get(f"/v1/cortex/jobs/{quote(job_id, safe='')}")
        if isinstance(res, dict) and isinstance(res.get("job"), dict):
            return res["job"]
        return res

    async def result(self, job_id: str) -> CortexJobResult:
        from urllib.parse import quote

        return await self._http.get(
            f"/v1/cortex/jobs/{quote(job_id, safe='')}/result"
        )

    async def wait_for_result(
        self,
        job_id: str,
        *,
        interval: float = 2.0,
        timeout: float = 120.0,
    ) -> CortexJobResult:
        """Poll :meth:`result` until terminal status; raise on timeout."""
        import time as _time

        deadline = _time.monotonic() + timeout
        while True:
            res = await self.result(job_id)
            if res.get("status") in CORTEX_TERMINAL_STATUSES:
                return res
            if _time.monotonic() + interval >= deadline:
                raise TimeoutError(
                    f"Cortex job {job_id} did not finish within {timeout}s "
                    f"(last status: {res.get('status')})"
                )
            await asyncio.sleep(interval)


class AsyncCortexResource:
    def __init__(self, http: AsyncHttpClient) -> None:
        self.jobs = AsyncCortexJobsResource(http)

    async def ask(
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
        """Ask the read-only ``complex_query`` analyst; get a cited answer.

        Launches a governed job and returns the parsed
        :class:`ComplexQueryResult`. Raises if the job fails or returns a
        non-``complex_query`` result. The analyst executes only when the
        platform's ``CORTEX_TOOL_RUNTIME_ENABLED`` flag is on.
        """
        ref = target_ref
        if ref is None and target_type == "project":
            ref = project_id
        if ref is None:
            raise ValueError(
                f"cortex.ask: target_ref is required for target_type '{target_type}'"
            )

        launched = await self.jobs.launch(
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

        if status not in CORTEX_TERMINAL_STATUSES:
            polled = await self.jobs.wait_for_result(
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
                f"cortex.ask: expected complex_query result, "
                f"got '{result.get('kind')}'"
            )
        return result  # type: ignore[return-value]


class AsyncDnaResource:
    """Async mirror of :class:`invariance.dna.DnaResource`."""

    def __init__(self, http: AsyncHttpClient) -> None:
        self._http = http

    async def list_objects(
        self,
        *,
        project_id: str | None = None,
        kind: str | None = None,
        q: str | None = None,
        cursor: str | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        """List DNA objects. Output: {data: [...], next_cursor}."""
        return await self._http.get(
            with_query(
                "/v1/dna/objects",
                project_id=project_id,
                kind=kind,
                q=q,
                cursor=cursor,
                limit=limit,
            )
        )

    async def list_object_mentions(
        self,
        *,
        project_id: str | None = None,
        event_id: str | None = None,
        chunk_id: str | None = None,
        object_id: str | None = None,
        mention_type: str | None = None,
        cursor: str | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        """List extracted object mentions. Output: {data: [...], next_cursor}."""
        return await self._http.get(
            with_query(
                "/v1/dna/object-mentions",
                project_id=project_id,
                event_id=event_id,
                chunk_id=chunk_id,
                object_id=object_id,
                mention_type=mention_type,
                cursor=cursor,
                limit=limit,
            )
        )

    async def list_edges(
        self,
        *,
        run_id: str | None = None,
        kind: str | None = None,
        entity_id: str | None = None,
        cursor: str | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        """List durable DNA edges (e.g. a run's operational graph)."""
        return await self._http.get(
            with_query(
                "/v1/dna/edges",
                run_id=run_id,
                kind=kind,
                entity_id=entity_id,
                cursor=cursor,
                limit=limit,
            )
        )

    async def list_edge_candidates(
        self,
        *,
        project_id: str | None = None,
        object_id: str | None = None,
        relation_kind: str | None = None,
        status: str | None = None,
        cursor: str | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        """List discovered edge candidates. Output: {data: [...], next_cursor}."""
        return await self._http.get(
            with_query(
                "/v1/dna/edge-candidates",
                project_id=project_id,
                object_id=object_id,
                relation_kind=relation_kind,
                status=status,
                cursor=cursor,
                limit=limit,
            )
        )

    async def accept_edge_candidate(
        self, id: str, *, project_id: str | None = None
    ) -> dict[str, Any]:
        """Accept a proposed candidate, making it eligible for promotion."""
        body: dict[str, Any] = {}
        if project_id is not None:
            body["project_id"] = project_id
        res = await self._http.post(f"/v1/dna/edge-candidates/{id}/accept", json=body)
        return res["candidate"]

    async def reject_edge_candidate(
        self, id: str, *, project_id: str | None = None
    ) -> dict[str, Any]:
        """Reject a candidate so it is never promoted."""
        body: dict[str, Any] = {}
        if project_id is not None:
            body["project_id"] = project_id
        res = await self._http.post(f"/v1/dna/edge-candidates/{id}/reject", json=body)
        return res["candidate"]

    async def promote_edge_candidate(
        self,
        id: str,
        *,
        dry_run: bool = False,
        project_id: str | None = None,
    ) -> dict[str, Any]:
        """Promote an accepted candidate into a durable semantic link.

        Output: ``{semantic_link, candidate, already_promoted, dry_run}``.
        """
        body: dict[str, Any] = {"dry_run": dry_run}
        if project_id is not None:
            body["project_id"] = project_id
        return await self._http.post(
            f"/v1/dna/edge-candidates/{id}/promote", json=body
        )


class AsyncMemoryResource:
    def __init__(self, http: AsyncHttpClient) -> None:
        self._http = http

    async def read(
        self,
        *,
        subject_type: MemorySubjectType,
        subject_id: str,
        key: str,
        used_for: str,
        run_id: str | None = None,
        node_id: str | None = None,
    ) -> MemoryReadResponse:
        body = _build_memory_read_body(
            subject_type=subject_type,
            subject_id=subject_id,
            key=key,
            used_for=used_for,
            run_id=run_id,
            node_id=node_id,
        )
        return await self._http.post("/v1/memory/read", json=body)

    async def write(
        self,
        *,
        subject_type: MemorySubjectType,
        subject_id: str,
        key: str,
        value: Any,
        used_for: str,
        run_id: str | None = None,
        node_id: str | None = None,
        source: MemorySource | None = None,
        confidence: float | None = None,
        provenance: list[EvidenceRef] | None = None,
        valid_until: str | None = None,
    ) -> MemoryWriteResponse:
        body = _build_memory_write_body(
            subject_type=subject_type,
            subject_id=subject_id,
            key=key,
            value=value,
            used_for=used_for,
            run_id=run_id,
            node_id=node_id,
            source=source,
            confidence=confidence,
            provenance=provenance,
            valid_until=valid_until,
        )
        return await self._http.post("/v1/memory/write", json=body)


class AsyncDatasetsResource:
    def __init__(self, http: AsyncHttpClient) -> None:
        self._http = http

    async def create(
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
        res = await self._http.post("/v1/eval-datasets", body)
        return res["dataset"]

    async def list(
        self,
        *,
        limit: int | None = None,
        cursor: str | None = None,
    ) -> EvalDatasetList:
        return await self._http.get(with_query("/v1/eval-datasets", limit=limit, cursor=cursor))

    async def get(self, dataset_id: str) -> EvalDataset:
        res = await self._http.get(f"/v1/eval-datasets/{dataset_id}")
        return res["dataset"]

    async def append_example(
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
        res = await self._http.post(f"/v1/eval-datasets/{dataset_id}/examples", body)
        return res["example"]

    async def list_examples(
        self,
        dataset_id: str,
        *,
        limit: int | None = None,
        cursor: str | None = None,
    ) -> EvalDatasetExampleList:
        return await self._http.get(
            with_query(f"/v1/eval-datasets/{dataset_id}/examples", limit=limit, cursor=cursor)
        )


class AsyncScorersResource:
    def __init__(self, http: AsyncHttpClient) -> None:
        self._http = http

    async def create(
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
        res = await self._http.post("/v1/eval-scorers", body)
        return res["scorer"]

    async def list(
        self,
        *,
        limit: int | None = None,
        cursor: str | None = None,
    ) -> EvalScorerList:
        return await self._http.get(with_query("/v1/eval-scorers", limit=limit, cursor=cursor))

    async def list_builtins(self) -> BuiltinScorerList:
        return await self._http.get("/v1/scorers")


class AsyncExperimentsResource:
    def __init__(self, http: AsyncHttpClient) -> None:
        self._http = http

    async def run(
        self,
        eval_run_id: str,
        *,
        scorer_specs: list[ScorerSpec],
        baseline_run_id: str | None = None,
    ) -> EvalRunRecord:
        body: dict[str, Any] = {"scorer_specs": scorer_specs}
        if baseline_run_id is not None:
            body["baseline_run_id"] = baseline_run_id
        res = await self._http.post(f"/v1/eval-runs/{eval_run_id}/experiment", body)
        return res["eval_run"]

    async def compare(self, eval_run_id: str, *, baseline_run_id: str) -> CompareResponse:
        return await self._http.get(
            with_query(f"/v1/eval-runs/{eval_run_id}/compare", baseline=baseline_run_id)
        )


class AsyncSuitesResource:
    def __init__(self, http: AsyncHttpClient) -> None:
        self._http = http

    async def create(
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
        res = await self._http.post("/v1/eval-suites", body)
        return res["suite"]

    async def list(
        self,
        *,
        limit: int | None = None,
        cursor: str | None = None,
    ) -> EvalSuiteList:
        return await self._http.get(with_query("/v1/eval-suites", limit=limit, cursor=cursor))

    async def get(self, suite_id: str) -> EvalSuiteRecord:
        res = await self._http.get(f"/v1/eval-suites/{suite_id}")
        return res["suite"]

    async def run(
        self,
        suite_id: str,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> EvalRunRecord:
        body: dict[str, Any] = {}
        if metadata is not None:
            body["metadata"] = metadata
        res = await self._http.post(f"/v1/eval-suites/{suite_id}/run", body)
        return res["eval_run"]


class AsyncCasesResource:
    def __init__(self, http: AsyncHttpClient) -> None:
        self._http = http

    async def create(
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
        res = await self._http.post(f"/v1/eval-suites/{suite_id}/cases", body)
        return res["case"]

    async def create_from_run(
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
        res = await self._http.post(f"/v1/eval-suites/{suite_id}/cases/from-run", body)
        return res["case"]

    async def list(
        self,
        suite_id: str,
        *,
        limit: int | None = None,
        cursor: str | None = None,
    ) -> EvalCaseList:
        return await self._http.get(
            with_query(f"/v1/eval-suites/{suite_id}/cases", limit=limit, cursor=cursor)
        )


class AsyncEvalRunsResource:
    def __init__(self, http: AsyncHttpClient) -> None:
        self._http = http

    async def get(self, eval_run_id: str) -> EvalRunRecord:
        res = await self._http.get(f"/v1/eval-runs/{eval_run_id}")
        return res["eval_run"]

    async def list_results(
        self,
        eval_run_id: str,
        *,
        limit: int | None = None,
        cursor: str | None = None,
    ) -> EvalResultRowList:
        return await self._http.get(
            with_query(f"/v1/eval-runs/{eval_run_id}/results", limit=limit, cursor=cursor)
        )


class AsyncEvalsResource:
    def __init__(self, http: AsyncHttpClient, runs: "AsyncRunsResource") -> None:
        self._http = http
        self._runs = runs
        self._monitors = AsyncMonitorsResource(http)
        self.datasets = AsyncDatasetsResource(http)
        self.scorers = AsyncScorersResource(http)
        self.suites = AsyncSuitesResource(http)
        self.cases = AsyncCasesResource(http)
        self.eval_runs = AsyncEvalRunsResource(http)
        self.experiments = AsyncExperimentsResource(http)

    async def seed_suite(
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
            seeded: SeedEvalSuiteResult = await self._http.post(
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
        dataset = await self.datasets.create(name=name, description=description, metadata=metadata)
        suite = await self.suites.create(
            name=suite_name or name,
            description=description,
            target_type=target_type,
            dataset_id=dataset["id"],
            metadata=metadata,
        )
        examples: list[EvalDatasetExample] = []
        cases: list[EvalCase] = []
        for i, row in enumerate(rows, start=1):
            example = await self.datasets.append_example(
                dataset["id"],
                input=row["input"],
                expected=row.get("expected"),
                metadata=row.get("metadata"),
            )
            examples.append(example)
            cases.append(
                await self.cases.create(
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
            result["eval_run"] = await self.suites.run(suite["id"])
        return result

    async def run_case(
        self,
        *,
        suite: str,
        case: str,
        handler: Callable[["AsyncRun"], Any],
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

        run = await self._runs.start(name=run_name, metadata=merged_metadata)
        run_id = run.run_id
        try:
            result = handler(run)
            if inspect.isawaitable(result):
                await result
            finished = await run.finish()
            run_id = finished["id"]
        except Exception as err:
            try:
                await run.fail(str(err))
            except Exception:
                pass
            raise

        if monitor_ids:
            for mid in monitor_ids:
                await self._monitors.evaluate(mid, run_id=run_id)

        findings = await self._findings_for_run(run_id)
        return {
            "run_id": run_id,
            "suite": suite,
            "case": case,
            "status": derive_status(findings),
            "findings": findings,
        }

    async def list_cases(
        self,
        *,
        suite: str,
        limit: int | None = None,
        cursor: str | None = None,
    ) -> EvalListResponse:
        path = with_query("/v1/runs", eval_suite=suite, limit=limit, cursor=cursor)
        res = await self._http.get(path)
        records: list[EvalCaseRecord] = []
        for run in res.get("data", []):
            meta = read_eval_metadata(run.get("metadata"))
            if meta is None:
                continue
            findings = await self._findings_for_run(run["id"])
            records.append(
                {
                    "run_id": run["id"],
                    "case": meta["case"],
                    "status": derive_status(findings),
                    "created_at": run["created_at"],
                }
            )
        return {"suite": suite, "runs": records, "next_cursor": res.get("next_cursor")}

    async def summarize(self, suite: str) -> EvalSummary:
        cursor: str | None = None
        passed = 0
        failed = 0
        for _ in range(20):
            res = await self.list_cases(suite=suite, limit=100, cursor=cursor)
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

    async def _findings_for_run(self, run_id: str) -> list[Finding]:
        path = with_query("/v1/findings", run_id=run_id, limit=100)
        res = await self._http.get(path)
        return res.get("data", [])


class AsyncOperatorsResource:
    def __init__(self, http: AsyncHttpClient) -> None:
        self._http = http

    async def me(self) -> Any:
        return await self._http.get("/v1/operators/me")

    async def create(
        self,
        *,
        name: str,
        project_id: str,
        operator_type: str | None = None,
        public_key: str | None = None,
        key_mode: str | None = None,
    ) -> Any:
        body: dict[str, object] = {"name": name, "project_id": project_id}
        if operator_type is not None:
            body["operator_type"] = operator_type
        if public_key is not None:
            body["public_key"] = public_key
        if key_mode is not None:
            body["key_mode"] = key_mode
        return await self._http.post("/v1/operators", json=body)

    async def list(
        self,
        *,
        project_id: str,
        operator_type: str | None = None,
    ) -> Any:
        return await self._http.get(
            with_query(
                "/v1/operators",
                project_id=project_id,
                operator_type=operator_type,
            )
        )

    async def get(self, id: str) -> Any:
        res = await self._http.get(f"/v1/operators/{id}")
        return res["operator"]


class AsyncSessionsResource:
    def __init__(self, http: AsyncHttpClient) -> None:
        self._http = http

    async def create(
        self,
        *,
        source: str,
        session_type: str | None = None,
        title: str | None = None,
        external_session_id: str | None = None,
        model: str | None = None,
        cwd: str | None = None,
        client_version: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Any:
        body: dict[str, Any] = {"source": source}
        for k, v in (
            ("session_type", session_type),
            ("title", title),
            ("external_session_id", external_session_id),
            ("model", model),
            ("cwd", cwd),
            ("client_version", client_version),
            ("metadata", metadata),
        ):
            if v is not None:
                body[k] = v
        res = await self._http.post("/v1/agent-sessions", json=body)
        return res["session"]

    async def list(
        self,
        *,
        project_id: str | None = None,
        operator_id: str | None = None,
        session_type: str | None = None,
        source: str | None = None,
        cursor: str | None = None,
        limit: int | None = None,
    ) -> Any:
        return await self._http.get(
            with_query(
                "/v1/agent-sessions",
                project_id=project_id,
                operator_id=operator_id,
                session_type=session_type,
                source=source,
                cursor=cursor,
                limit=limit,
            )
        )

    async def get(self, id: str) -> Any:
        res = await self._http.get(f"/v1/agent-sessions/{id}")
        return res["session"]

    async def append_events(
        self, id: str, events: list[dict[str, Any]]
    ) -> Any:
        return await self._http.post(
            f"/v1/agent-sessions/{id}/events", json={"events": events}
        )

    async def from_claude_code(self, **kwargs: Any) -> Any:
        kwargs.setdefault("source", "claude_code")
        kwargs.setdefault("session_type", "coding")
        return await self.create(**kwargs)

    async def from_meeting_notes(self, **kwargs: Any) -> Any:
        kwargs.setdefault("source", "meeting")
        kwargs.setdefault("session_type", "meeting")
        return await self.create(**kwargs)

    async def from_granola_note(self, **kwargs: Any) -> Any:
        kwargs.setdefault("source", "granola_note")
        kwargs.setdefault("session_type", "note")
        return await self.create(**kwargs)


class AsyncWorkflowCasesResource:
    """Async sibling of :class:`invariance.CasesResource` (workflow cases)."""

    def __init__(self, http: AsyncHttpClient) -> None:
        self._http = http

    async def create(
        self,
        *,
        workflow_key: str,
        id: str | None = None,
        tenant_id: str | None = None,
        end_user_id: str | None = None,
        owner: str | None = None,
        custom_attrs: dict[str, Any] | None = None,
        tags: list[str] | None = None,
        opened_at: str | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"workflow_key": workflow_key}
        for k, v in (
            ("id", id),
            ("tenant_id", tenant_id),
            ("end_user_id", end_user_id),
            ("owner", owner),
            ("custom_attrs", custom_attrs),
            ("tags", tags),
            ("opened_at", opened_at),
        ):
            if v is not None:
                body[k] = v
        res = await self._http.post("/v1/cases", json=body)
        return res["case"]

    async def get(self, id: str) -> dict[str, Any]:
        res = await self._http.get(f"/v1/cases/{id}")
        return res["case"]

    async def evidence(self, id: str) -> dict[str, Any]:
        return await self._http.get(f"/v1/cases/{id}/evidence")

    async def list_events(
        self, id: str, *, cursor: str | None = None, limit: int | None = None
    ) -> WorkflowEventList:
        return await self._http.get(
            with_query(f"/v1/cases/{id}/events", cursor=cursor, limit=limit)
        )

    async def create_event(
        self,
        id: str,
        *,
        type: str,
        actor_type: WorkflowEventActorType | None = None,
        actor_id: str | None = None,
        payload: dict[str, Any] | None = None,
        evidence_node_ids: list[str] | None = None,
        evidence_refs: list[dict[str, Any]] | None = None,
        occurred_at: str | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"type": type}
        for k, v in (
            ("actor_type", actor_type),
            ("actor_id", actor_id),
            ("payload", payload),
            ("evidence_node_ids", evidence_node_ids),
            ("evidence_refs", evidence_refs),
            ("occurred_at", occurred_at),
        ):
            if v is not None:
                body[k] = v
        res = await self._http.post(f"/v1/cases/{id}/events", json=body)
        return res["event"]

    async def list(
        self,
        *,
        tenant_id: str | None = None,
        end_user_id: str | None = None,
        workflow_key: str | None = None,
        status: str | None = None,
        outcome: str | None = None,
        tags: str | None = None,
        cursor: str | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        return await self._http.get(
            with_query(
                "/v1/cases",
                tenant_id=tenant_id,
                end_user_id=end_user_id,
                workflow_key=workflow_key,
                status=status,
                outcome=outcome,
                tags=tags,
                cursor=cursor,
                limit=limit,
            )
        )

    async def update(
        self,
        id: str,
        *,
        status: str | None = None,
        outcome: str | None = None,
        outcome_value_usd: float | None = None,
        owner: str | None = None,
        custom_attrs: dict[str, Any] | None = None,
        tags: list[str] | None = None,
        closed_at: str | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {}
        for k, v in (
            ("status", status),
            ("outcome", outcome),
            ("outcome_value_usd", outcome_value_usd),
            ("owner", owner),
            ("custom_attrs", custom_attrs),
            ("tags", tags),
            ("closed_at", closed_at),
        ):
            if v is not None:
                body[k] = v
        res = await self._http.patch(f"/v1/cases/{id}", json=body)
        return res["case"]

    async def close(
        self,
        id: str,
        *,
        outcome: str,
        value_usd: float | None = None,
        closed_at: str | None = None,
    ) -> dict[str, Any]:
        return await self.update(
            id,
            status="closed",
            outcome=outcome,
            outcome_value_usd=value_usd,
            closed_at=closed_at,
        )

    @asynccontextmanager
    async def with_case(
        self, case_or_id: dict[str, Any] | str
    ) -> AsyncIterator[None]:
        if isinstance(case_or_id, str):
            c = await self.get(case_or_id)
        else:
            c = case_or_id
        ctx = _CaseContext(
            case_id=c["id"],
            tenant_id=c.get("tenant_id"),
            end_user_id=c.get("end_user_id"),
        )
        token = _current_case.set(ctx)
        try:
            yield
        finally:
            _current_case.reset(token)


class AsyncEventsResource:
    """Async sibling of :class:`invariance.EventsResource`."""

    def __init__(self, http: AsyncHttpClient) -> None:
        self._http = http

    async def list(
        self,
        *,
        case_id: str | None = None,
        tenant_id: str | None = None,
        end_user_id: str | None = None,
        workflow_key: str | None = None,
        type: str | None = None,
        actor_type: WorkflowEventActorType | None = None,
        actor_id: str | None = None,
        from_: str | None = None,
        to: str | None = None,
        cursor: str | None = None,
        limit: int | None = None,
    ) -> WorkflowEventList:
        return await self._http.get(
            with_query(
                "/v1/events",
                case_id=case_id,
                tenant_id=tenant_id,
                end_user_id=end_user_id,
                workflow_key=workflow_key,
                type=type,
                actor_type=actor_type,
                actor_id=actor_id,
                **{"from": from_},
                to=to,
                cursor=cursor,
                limit=limit,
            )
        )

    async def list_for_case(
        self, case_id: str, *, cursor: str | None = None, limit: int | None = None
    ) -> WorkflowEventList:
        return await self._http.get(
            with_query(f"/v1/cases/{case_id}/events", cursor=cursor, limit=limit)
        )

    async def create(
        self,
        case_id: str,
        *,
        type: str,
        actor_type: WorkflowEventActorType | None = None,
        actor_id: str | None = None,
        payload: dict[str, Any] | None = None,
        evidence_node_ids: list[str] | None = None,
        evidence_refs: list[dict[str, Any]] | None = None,
        idempotency_key: str | None = None,
        occurred_at: str | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"type": type}
        for k, v in (
            ("actor_type", actor_type),
            ("actor_id", actor_id),
            ("payload", payload),
            ("evidence_node_ids", evidence_node_ids),
            ("evidence_refs", evidence_refs),
            ("idempotency_key", idempotency_key),
            ("occurred_at", occurred_at),
        ):
            if v is not None:
                body[k] = v
        res = await self._http.post(f"/v1/cases/{case_id}/events", json=body)
        return res["event"]


class AsyncCapturesResource:
    """Async sibling of :class:`invariance.CapturesResource`."""

    def __init__(self, http: AsyncHttpClient) -> None:
        self._http = http

    async def create(
        self,
        *,
        source: str,
        session_type: str | None = None,
        title: str | None = None,
        external_session_id: str | None = None,
        model: str | None = None,
        cwd: str | None = None,
        client_version: str | None = None,
        run_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"source": source}
        for k, v in (
            ("session_type", session_type),
            ("title", title),
            ("external_session_id", external_session_id),
            ("model", model),
            ("cwd", cwd),
            ("client_version", client_version),
            ("run_id", run_id),
            ("metadata", metadata),
            ("tags", tags),
        ):
            if v is not None:
                body[k] = v
        res = await self._http.post("/v1/captures", json=body)
        return res["session"]

    async def get(self, id: str) -> dict[str, Any]:
        res = await self._http.get(f"/v1/captures/{id}")
        return res["session"]

    async def list(
        self,
        *,
        project_id: str | None = None,
        operator_id: str | None = None,
        session_type: str | None = None,
        source: str | None = None,
        run_id: str | None = None,
        tags: str | None = None,
        cursor: str | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        return await self._http.get(
            with_query(
                "/v1/captures",
                project_id=project_id,
                operator_id=operator_id,
                session_type=session_type,
                source=source,
                run_id=run_id,
                tags=tags,
                cursor=cursor,
                limit=limit,
            )
        )

    async def list_links(self, id: str) -> dict[str, Any]:
        res = await self._http.get(f"/v1/captures/{id}/links")
        links = res.get("links", [])
        run_id = next((l["run_id"] for l in links if l.get("run_id")), None)
        return {"links": links, "run_id": run_id}


class AsyncGuardrailsResource:
    """Async sibling of :class:`invariance.GuardrailsResource`."""

    def __init__(self, http: AsyncHttpClient) -> None:
        self._http = http

    async def list(
        self,
        *,
        cursor: str | None = None,
        limit: int | None = None,
        status: GuardrailStatus | None = None,
        recipe_id: str | None = None,
    ) -> GuardrailList:
        return await self._http.get(
            with_query(
                "/v1/guardrails",
                cursor=cursor,
                limit=limit,
                status=status,
                recipe_id=recipe_id,
            )
        )

    async def get(self, id: str) -> Guardrail:
        res = await self._http.get(f"/v1/guardrails/{id}")
        return res["guardrail"]

    async def create(
        self,
        *,
        title: str,
        recipe_id: str | None = None,
        finding_id: str | None = None,
        rule: str | None = None,
        mode: GuardrailMode | None = None,
        status: GuardrailStatus | None = None,
        agent_id: str | None = None,
    ) -> Guardrail:
        body: dict[str, Any] = {"title": title}
        for k, v in (
            ("recipe_id", recipe_id),
            ("finding_id", finding_id),
            ("rule", rule),
            ("mode", mode),
            ("status", status),
            ("agent_id", agent_id),
        ):
            if v is not None:
                body[k] = v
        res = await self._http.post("/v1/guardrails", json=body)
        return res["guardrail"]

    async def update(
        self,
        id: str,
        *,
        mode: GuardrailMode | None = None,
        status: GuardrailStatus | None = None,
        monitor_id: str | None = None,
    ) -> Guardrail:
        body: dict[str, Any] = {}
        for k, v in (("mode", mode), ("status", status), ("monitor_id", monitor_id)):
            if v is not None:
                body[k] = v
        res = await self._http.patch(f"/v1/guardrails/{id}", json=body)
        return res["guardrail"]

    async def promote(self, id: str, *, to: GuardrailStatus) -> Guardrail:
        res = await self._http.post(f"/v1/guardrails/{id}/promote", json={"to": to})
        return res["guardrail"]


class AsyncRecipesResource:
    """Async sibling of :class:`invariance.RecipesResource`."""

    def __init__(self, http: AsyncHttpClient) -> None:
        self._http = http

    async def list(
        self, *, cursor: str | None = None, limit: int | None = None
    ) -> RecipeList:
        return await self._http.get(
            with_query("/v1/recipes", cursor=cursor, limit=limit)
        )

    async def get(self, id_or_slug: str) -> Recipe:
        res = await self._http.get(f"/v1/recipes/{id_or_slug}")
        return res["recipe"]

    async def update(
        self,
        id: str,
        *,
        enabled: bool | None = None,
        default_mode: GuardrailMode | None = None,
    ) -> Recipe:
        body: dict[str, Any] = {}
        if enabled is not None:
            body["enabled"] = enabled
        if default_mode is not None:
            body["default_mode"] = default_mode
        res = await self._http.patch(f"/v1/recipes/{id}", json=body)
        return res["recipe"]


class AsyncDivergencesResource:
    """Async sibling of :class:`invariance.DivergencesResource`."""

    def __init__(self, http: AsyncHttpClient) -> None:
        self._http = http

    async def list(
        self,
        *,
        run_id: str | None = None,
        kind: DivergenceKind | None = None,
        severity: Severity | None = None,
        status: DivergenceStatus | None = None,
        cursor: str | None = None,
        limit: int | None = None,
    ) -> DivergenceList:
        return await self._http.get(
            with_query(
                "/v1/divergences",
                run_id=run_id,
                kind=kind,
                severity=severity,
                status=status,
                cursor=cursor,
                limit=limit,
            )
        )

    async def get(self, id: str) -> Divergence:
        res = await self._http.get(f"/v1/divergences/{id}")
        return res["divergence"]

    async def update(self, id: str, *, status: DivergenceStatus) -> Divergence:
        res = await self._http.patch(
            f"/v1/divergences/{id}", json={"status": status}
        )
        return res["divergence"]


class AsyncSavedViewsResource:
    """Async sibling of :class:`invariance.SavedViewsResource`."""

    def __init__(self, http: AsyncHttpClient) -> None:
        self._http = http

    async def list(self) -> SavedViewList:
        return await self._http.get("/v1/saved-views")

    async def create(
        self,
        *,
        name: str,
        source: QuerySource,
        spec: QuerySpec,
        viz: DashboardViz | None = None,
        visibility: SavedViewVisibility | None = None,
    ) -> SavedView:
        body: dict[str, Any] = {"name": name, "source": source, "spec": spec}
        if viz is not None:
            body["viz"] = viz
        if visibility is not None:
            body["visibility"] = visibility
        res = await self._http.post("/v1/saved-views", json=body)
        return res["view"]

    async def get(self, id: str) -> SavedView:
        res = await self._http.get(f"/v1/saved-views/{id}")
        return res["view"]

    async def update(
        self,
        id: str,
        *,
        name: str | None = None,
        source: QuerySource | None = None,
        spec: QuerySpec | None = None,
        viz: DashboardViz | None = None,
        visibility: SavedViewVisibility | None = None,
    ) -> SavedView:
        body: dict[str, Any] = {}
        for k, v in (
            ("name", name),
            ("source", source),
            ("spec", spec),
            ("viz", viz),
            ("visibility", visibility),
        ):
            if v is not None:
                body[k] = v
        res = await self._http.patch(f"/v1/saved-views/{id}", json=body)
        return res["view"]

    async def delete(self, id: str) -> None:
        await self._http.delete(f"/v1/saved-views/{id}")

    async def run(
        self,
        *,
        saved_view_id: str | None = None,
        source: QuerySource | None = None,
        spec: QuerySpec | None = None,
    ) -> QueryResult:
        if saved_view_id is not None and source is not None:
            raise ValueError(
                "run() takes exactly one of saved_view_id or source, not both"
            )
        if saved_view_id is None and source is None:
            raise ValueError("run() requires either saved_view_id or source")
        if saved_view_id is not None:
            body: dict[str, Any] = {"saved_view_id": saved_view_id}
        else:
            body = {"source": source}
            if spec is not None:
                body["spec"] = spec
        res = await self._http.post("/v1/saved-views/run", json=body)
        return res["result"]


class AsyncReceiptsResource:
    """Async sibling of :class:`invariance.ReceiptsResource`.

    ``create`` / ``create_batch`` require an agent API key (403 on operator
    tokens). ``list`` / ``get`` accept an agent or operator key.
    """

    def __init__(self, http: AsyncHttpClient) -> None:
        self._http = http

    async def create(
        self,
        *,
        source: ExternalReceiptSource,
        kind: str,
        run_id: str | None = None,
        node_id: str | None = None,
        external_id: str | None = None,
        occurred_at: str | None = None,
        business_object_type: str | None = None,
        business_object_id: str | None = None,
        subject_type: str | None = None,
        subject_id: str | None = None,
        correlation_keys: dict[str, str] | None = None,
        payload: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ExternalReceipt:
        body = _build_receipt_body(
            source=source,
            kind=kind,
            run_id=run_id,
            node_id=node_id,
            external_id=external_id,
            occurred_at=occurred_at,
            business_object_type=business_object_type,
            business_object_id=business_object_id,
            subject_type=subject_type,
            subject_id=subject_id,
            correlation_keys=correlation_keys,
            payload=payload,
            metadata=metadata,
        )
        res = await self._http.post("/v1/receipts", json=body)
        return res["receipt"]

    async def create_batch(
        self, receipts: list[dict[str, Any]]
    ) -> list[ExternalReceipt]:
        res = await self._http.post(
            "/v1/receipts/batch", json={"receipts": receipts}
        )
        return res["receipts"]

    async def list(
        self,
        *,
        run_id: str | None = None,
        node_id: str | None = None,
        source: ExternalReceiptSource | None = None,
        kind: str | None = None,
        external_id: str | None = None,
        business_object_type: str | None = None,
        business_object_id: str | None = None,
        cursor: str | None = None,
        limit: int | None = None,
    ) -> ExternalReceiptList:
        return await self._http.get(
            with_query(
                "/v1/receipts",
                run_id=run_id,
                node_id=node_id,
                source=source,
                kind=kind,
                external_id=external_id,
                business_object_type=business_object_type,
                business_object_id=business_object_id,
                cursor=cursor,
                limit=limit,
            )
        )

    async def get(self, id: str) -> ExternalReceipt:
        res = await self._http.get(f"/v1/receipts/{id}")
        return res["receipt"]


class AsyncWorkflowObservabilityResource:
    """Async sibling of :class:`invariance.WorkflowObservabilityResource`."""

    def __init__(self, http: AsyncHttpClient) -> None:
        self._http = http

    async def list(self) -> WorkflowObservabilityRollupList:
        return await self._http.get("/v1/workflow-observability")

    async def get(self, workflow_key: str) -> WorkflowObservabilityRollup:
        res = await self._http.get(f"/v1/workflow-observability/{workflow_key}")
        return res["rollup"]

    async def executions(
        self, workflow_key: str
    ) -> WorkflowExecutionHealthList:
        return await self._http.get(
            f"/v1/workflow-observability/{workflow_key}/executions"
        )


class AsyncMetricsResource:
    """Async sibling of :class:`invariance.MetricsResource`."""

    def __init__(self, http: AsyncHttpClient) -> None:
        self._http = http

    async def overview(
        self, *, window_hours: int | None = None
    ) -> OverviewMetrics:
        res = await self._http.get(
            with_query("/v1/metrics/overview", window_hours=window_hours)
        )
        return res["metrics"]

    async def agents(
        self, *, window_hours: int | None = None
    ) -> list[AgentUsage]:
        res = await self._http.get(
            with_query("/v1/metrics/agents", window_hours=window_hours)
        )
        return res["usage"]


class AsyncInvariance:
    def __init__(
        self,
        api_key: str | None = None,
        api_url: str | None = None,
        *,
        signing_key: str | None = None,
        features: dict[str, bool] | None = None,
        retry_policy: RetryPolicy | None = None,
    ) -> None:
        cfg = resolve_config(
            api_key=api_key,
            api_url=api_url,
            signing_key=signing_key,
            features=features,
        )
        self.config = cfg
        self.features = cfg.features
        self._http = AsyncHttpClient(
            cfg.api_url,
            cfg.api_key,
            retry_policy=retry_policy,
        )
        self.runs = AsyncRunsResource(self._http, cfg.signing_key)
        self.nodes = AsyncNodesResource(self._http)
        self.agents = AsyncAgentsResource(self._http)
        self.monitors = AsyncMonitorsResource(self._http)
        self.monitor_routes = AsyncMonitorRoutesResource(self._http)
        self.signals = AsyncSignalsResource(self._http)
        self.proofs = AsyncProofsResource(self._http)
        self.findings = AsyncFindingsResource(self._http)
        self.reviews = AsyncReviewsResource(self._http)
        self.narratives = AsyncNarrativesResource(self._http)
        self.node_types = AsyncNodeTypesResource(self._http)
        self.kb = AsyncKbResource(self._http)
        self.ask = AsyncAskResource(self._http)
        self.memory = AsyncMemoryResource(self._http)
        self.evals = AsyncEvalsResource(self._http, self.runs)
        self.operators = AsyncOperatorsResource(self._http)
        self.sessions = AsyncSessionsResource(self._http)
        self.cortex = AsyncCortexResource(self._http)
        self.dna = AsyncDnaResource(self._http)
        self.cases = AsyncWorkflowCasesResource(self._http)
        self.events = AsyncEventsResource(self._http)
        self.captures = AsyncCapturesResource(self._http)
        self.guardrails = AsyncGuardrailsResource(self._http)
        self.recipes = AsyncRecipesResource(self._http)
        self.divergences = AsyncDivergencesResource(self._http)
        self.saved_views = AsyncSavedViewsResource(self._http)
        self.receipts = AsyncReceiptsResource(self._http)
        self.workflow_observability = AsyncWorkflowObservabilityResource(self._http)
        self.metrics = AsyncMetricsResource(self._http)

    async def aclose(self) -> None:
        await self._http.aclose()

    # Parity alias with sync Invariance.close(). Async-correct: must be awaited.
    close = aclose

    async def __aenter__(self) -> "AsyncInvariance":
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.aclose()


F = TypeVar("F", bound=Callable[..., Any])


def async_trace(
    run: AsyncRun,
    action_type: str | None = None,
    *,
    capture_args: bool = True,
    capture_return: bool = True,
) -> Callable[[F], F]:
    """Async counterpart of :func:`invariance.trace`. Wraps a coroutine fn."""

    def decorator(fn: F) -> F:
        label = action_type or fn.__qualname__
        sig = inspect.signature(fn)

        @functools.wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            input_payload: Any = None
            if capture_args:
                try:
                    bound = sig.bind(*args, **kwargs)
                    bound.apply_defaults()
                    input_payload = dict(bound.arguments)
                except TypeError:
                    input_payload = {"args": args, "kwargs": kwargs}
            async with run.step(label, input=input_payload) as s:
                result = await fn(*args, **kwargs)
                if capture_return:
                    s.output = result
                return result

        return wrapper  # type: ignore[return-value]

    return decorator
