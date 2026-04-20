from __future__ import annotations

import contextvars
import threading
import traceback
from typing import Any

from ._types import RunList
from .client import HttpClient
from ._internal import build_node_body, now_ms as _now_ms, random_node_id as _random_node_id
from ._query import with_query
from .signals import SignalsResource


BATCH_MAX = 100


# Context var tracking the currently-active Step in this sync context.
# Used by nested `run.step(...)` and by `@trace` to auto-fill parent_id.
_current_step: contextvars.ContextVar["Step | None"] = contextvars.ContextVar(
    "invariance_current_step", default=None
)


class Step:
    """A single unit of work inside a Run.

    Holds mutable ``input``, ``output``, ``error``, ``metadata``,
    ``custom_fields``. When used as a context manager, on exit it emits a
    node carrying the captured values, its elapsed duration, and a
    ``parent_id`` pointing at the enclosing step (if any).

    Exceptions raised inside the ``with`` block are stored in ``error``
    and then re-raised.
    """

    def __init__(
        self,
        run: "Run",
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

    def __enter__(self) -> "Step":
        parent = _current_step.get()
        self._parent_id = parent.id if parent is not None else None
        self._start_ms = _now_ms()
        self._token = _current_step.set(self)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        try:
            if exc_val is not None and self.error is None:
                self.error = {
                    "type": exc_type.__name__ if exc_type else "Exception",
                    "message": str(exc_val),
                    "traceback": "".join(traceback.format_exception(exc_type, exc_val, exc_tb)),
                }
            duration_ms = _now_ms() - (self._start_ms or _now_ms())
            self._run._emit(
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
                _current_step.reset(self._token)
                self._token = None
        return False  # always re-raise


class Run:
    """A developer-facing agent run.

    Use as a context manager:

        with inv.runs.start(name="support") as run:
            with run.step("plan") as s:
                s.output = {...}

    On normal exit the run is marked ``completed``; if an exception
    escapes the ``with`` block the run is marked ``failed``.

    Node writes are buffered by default and flushed in batches of up to
    ``BATCH_MAX`` (100) on buffer fill, on ``flush()``, or on exit. Pass
    ``buffered=False`` to ``RunsResource.start`` for per-step POSTs.

    A per-run :class:`threading.Lock` serializes writes so two threads
    inside one run cannot produce a branched chain. (The backend has no
    conflict detection for concurrent writes to the same run.)
    """

    def __init__(
        self,
        http: HttpClient,
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
        self._lock = threading.Lock()
        self._closed = False
        self._signals = SignalsResource(http)

    @property
    def run_id(self) -> str:
        return self._session["id"]

    @property
    def name(self) -> str:
        return self._session.get("name", "")

    @property
    def status(self) -> str:
        return self._session.get("status", "open")

    # ── Context manager ────────────────────────────────────────────────

    def __enter__(self) -> "Run":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        try:
            self.flush()
        finally:
            if self._closed:
                return False
            if exc_val is not None:
                self.fail(error=str(exc_val))
            else:
                self.finish()
        return False

    # ── Step ───────────────────────────────────────────────────────────

    def step(
        self,
        action_type: str,
        *,
        input: Any | None = None,
        output: Any | None = None,
        metadata: dict[str, Any] | None = None,
        custom_fields: dict[str, Any] | None = None,
        type: str | None = None,
    ) -> Step:
        return Step(
            self,
            action_type,
            input=input,
            output=output,
            metadata=metadata,
            custom_fields=custom_fields,
            type=type,
        )

    # ── Emit / flush ───────────────────────────────────────────────────

    def _emit(
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
        with self._lock:
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
                self._flush_locked()

    def flush(self) -> None:
        with self._lock:
            self._flush_locked()

    def _flush_locked(self) -> None:
        if not self._buffer:
            return
        # Backend accepts up to 100 nodes per POST.
        while self._buffer:
            chunk = self._buffer[:BATCH_MAX]
            self._buffer = self._buffer[BATCH_MAX:]
            res = self._http.post("/v1/nodes", json=chunk)
            nodes = res["data"]
            if nodes:
                last = nodes[-1]
                if "hash" in last and not self._signing_key:
                    # For unsigned flows the server computes hashes — track
                    # the tail so a later signed write in the same run (rare
                    # but legal) starts from the right previous_hash.
                    self._last_hash = last["hash"]

    # ── Signals ────────────────────────────────────────────────────────

    def signal(self, spec: dict[str, Any]) -> dict[str, Any]:
        """Emit a signal attached to the current run (and last node by default).

        ``spec`` is a body dict — typically the output of
        :meth:`SignalType.signal` (``run.signal(DangerousOutput.signal(...))``).
        For ad-hoc one-off signals, call
        ``inv.signals.emit(severity=..., title=...)`` directly.
        """
        self.flush()
        merged = dict(spec)
        if "severity" not in merged or "title" not in merged:
            raise ValueError("signal spec requires severity and title")
        merged.setdefault("run_id", self.run_id)
        if "node_id" not in merged and self._last_node_id is not None:
            merged["node_id"] = self._last_node_id
        return self._signals.emit(**merged)

    # ── Lifecycle ──────────────────────────────────────────────────────

    def verify(self) -> dict[str, Any]:
        return self._http.get(f"/v1/runs/{self.run_id}/verify")

    def finish(self) -> dict[str, Any]:
        self.flush()
        res = self._http.patch(
            f"/v1/runs/{self.run_id}",
            json={"status": "completed"},
        )
        self._closed = True
        return res["run"]

    def fail(self, error: str | None = None) -> dict[str, Any]:
        self.flush()
        body: dict[str, Any] = {"status": "failed"}
        if error:
            body["metadata"] = {"error": error}
        res = self._http.patch(f"/v1/runs/{self.run_id}", json=body)
        self._closed = True
        return res["run"]


class RunsResource:
    def __init__(self, http: HttpClient, signing_key: str | None = None) -> None:
        self._http = http
        self._signing_key = signing_key

    def start(
        self,
        name: str | None = None,
        metadata: dict[str, Any] | None = None,
        *,
        signing_key: str | None = None,
        buffered: bool = True,
    ) -> Run:
        body: dict[str, Any] = {}
        if name is not None:
            body["name"] = name
        if metadata is not None:
            body["metadata"] = metadata
        res = self._http.post("/v1/runs", json=body)
        return Run(
            self._http,
            res["run"],
            signing_key or self._signing_key,
            buffered=buffered,
        )

    def list(
        self,
        *,
        cursor: str | None = None,
        limit: int | None = None,
    ) -> RunList:
        return self._http.get(with_query("/v1/runs", cursor=cursor, limit=limit))

    def get(self, id: str) -> Run:
        res = self._http.get(f"/v1/runs/{id}")
        return Run(self._http, res["run"], self._signing_key)
