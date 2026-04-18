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
from typing import Any, Callable, TypeVar
from urllib.parse import urlencode

import httpx

from .client import InvarianceApiError
from .monitors import MonitorSpec, compile_monitor
from ._internal import build_node_body, now_ms as _now_ms, random_node_id as _random_node_id

DEFAULT_API_URL = "https://api.useinvariance.com"
BATCH_MAX = 100


_current_async_step: contextvars.ContextVar["AsyncStep | None"] = contextvars.ContextVar(
    "invariance_current_async_step", default=None
)


class AsyncHttpClient:
    def __init__(self, base_url: str, api_key: str) -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=30.0,
        )

    async def request(self, method: str, path: str, *, json: Any | None = None) -> Any:
        res = await self._client.request(method, path, json=json)
        if res.status_code >= 400:
            body: dict[str, Any] = {}
            try:
                body = res.json()
            except Exception:
                pass
            err = body.get("error", {})
            raise InvarianceApiError(
                status=res.status_code,
                code=err.get("code", "unknown"),
                message=err.get("message", f"HTTP {res.status_code}"),
                details=err.get("details"),
                request_id=err.get("request_id"),
            )
        return res.json()

    async def get(self, path: str) -> Any:
        return await self.request("GET", path)

    async def post(self, path: str, json: Any | None = None) -> Any:
        return await self.request("POST", path, json=json)

    async def patch(self, path: str, json: Any | None = None) -> Any:
        return await self.request("PATCH", path, json=json)

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
    ) -> None:
        self._run = run
        self.action_type = action_type
        self.type = type
        self.input = input
        self.output = output
        self.error: Any | None = None
        self.metadata = dict(metadata) if metadata else None
        self.custom_fields = dict(custom_fields) if custom_fields else None
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
    ) -> AsyncStep:
        return AsyncStep(
            self,
            action_type,
            input=input,
            output=output,
            metadata=metadata,
            custom_fields=custom_fields,
            type=type,
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
        severity: str | None = None,
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

    async def verify(self) -> dict[str, Any]:
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

    async def list(self, *, cursor: str | None = None, limit: int | None = None) -> dict[str, Any]:
        params: dict[str, str] = {}
        if cursor:
            params["cursor"] = cursor
        if limit:
            params["limit"] = str(limit)
        qs = f"?{urlencode(params)}" if params else ""
        return await self._http.get(f"/v1/runs{qs}")

    async def get(self, id: str) -> AsyncRun:
        res = await self._http.get(f"/v1/runs/{id}")
        return AsyncRun(self._http, res["run"], self._signing_key)


class AsyncNodesResource:
    def __init__(self, http: AsyncHttpClient) -> None:
        self._http = http

    async def write(
        self,
        run_id: str,
        nodes: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        body = [{"run_id": run_id, **n} for n in nodes]
        res = await self._http.post("/v1/nodes", json=body)
        return res["data"]

    async def list(
        self,
        run_id: str,
        *,
        cursor: str | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        params: dict[str, str] = {}
        if cursor:
            params["cursor"] = cursor
        if limit:
            params["limit"] = str(limit)
        qs = f"?{urlencode(params)}" if params else ""
        return await self._http.get(f"/v1/runs/{run_id}/nodes{qs}")


class AsyncAgentsResource:
    def __init__(self, http: AsyncHttpClient) -> None:
        self._http = http

    async def me(self) -> dict[str, Any]:
        return await self._http.get("/v1/agents/me")

    async def set_public_key(self, public_key: str) -> dict[str, Any]:
        res = await self._http.request(
            "PUT", "/v1/agents/me/key", json={"public_key": public_key}
        )
        return res["agent"]


class AsyncMonitorsResource:
    def __init__(self, http: AsyncHttpClient) -> None:
        self._http = http

    async def create(self, spec: MonitorSpec) -> dict[str, Any]:
        body = {"name": spec.name, "definition": compile_monitor(spec), "severity": spec.severity}
        res = await self._http.post("/v1/monitors", json=body)
        return res["monitor"]

    async def get(self, id: str) -> dict[str, Any]:
        res = await self._http.get(f"/v1/monitors/{id}")
        return res["monitor"]

    async def list(
        self,
        *,
        cursor: str | None = None,
        limit: int | None = None,
        status: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, str] = {}
        if cursor:
            params["cursor"] = cursor
        if limit:
            params["limit"] = str(limit)
        if status:
            params["status"] = status
        qs = f"?{urlencode(params)}" if params else ""
        return await self._http.get(f"/v1/monitors{qs}")

    async def update(
        self,
        id: str,
        *,
        name: str | None = None,
        severity: str | None = None,
        status: str | None = None,
    ) -> dict[str, Any]:
        patch: dict[str, Any] = {}
        if name is not None:
            patch["name"] = name
        if severity is not None:
            patch["severity"] = severity
        if status is not None:
            patch["status"] = status
        res = await self._http.request("PUT", f"/v1/monitors/{id}", json=patch)
        return res["monitor"]

    async def pause(self, id: str) -> dict[str, Any]:
        return await self.update(id, status="paused")

    async def resume(self, id: str) -> dict[str, Any]:
        return await self.update(id, status="active")


class AsyncSignalsResource:
    def __init__(self, http: AsyncHttpClient) -> None:
        self._http = http

    async def emit(
        self,
        *,
        severity: str,
        title: str,
        message: str | None = None,
        type: str | None = None,
        data: Any | None = None,
        node_id: str | None = None,
        run_id: str | None = None,
    ) -> dict[str, Any]:
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
    ) -> dict[str, Any]:
        params: dict[str, str] = {}
        if cursor:
            params["cursor"] = cursor
        if limit:
            params["limit"] = str(limit)
        qs = f"?{urlencode(params)}" if params else ""
        return await self._http.get(f"/v1/signals{qs}")

    async def get(self, id: str) -> dict[str, Any]:
        res = await self._http.get(f"/v1/signals/{id}")
        return res["signal"]

    async def acknowledge(self, id: str) -> dict[str, Any]:
        res = await self._http.patch(f"/v1/signals/{id}/acknowledge")
        return res["signal"]


class AsyncInvariance:
    def __init__(
        self,
        api_key: str,
        api_url: str | None = None,
        *,
        signing_key: str | None = None,
    ) -> None:
        if not api_key:
            raise ValueError("api_key is required")
        self._http = AsyncHttpClient(api_url or DEFAULT_API_URL, api_key)
        self.runs = AsyncRunsResource(self._http, signing_key)
        self.nodes = AsyncNodesResource(self._http)
        self.agents = AsyncAgentsResource(self._http)
        self.monitors = AsyncMonitorsResource(self._http)
        self.signals = AsyncSignalsResource(self._http)

    async def aclose(self) -> None:
        await self._http.aclose()

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
