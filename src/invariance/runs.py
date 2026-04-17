from __future__ import annotations

import contextvars
import secrets
import threading
import time
import traceback
from typing import Any, Iterator
from urllib.parse import urlencode
from contextlib import contextmanager

from .client import HttpClient
from .crypto import hash_node_payload, sign_ed25519


BATCH_MAX = 100


def _random_node_id() -> str:
    return f"node_{secrets.token_hex(8)}"


def _now_ms() -> int:
    return int(time.time() * 1000)


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
    ) -> None:
        self._run = run
        self.action_type = action_type
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
        self._buffered = buffered
        self._buffer: list[dict[str, Any]] = []
        self._lock = threading.Lock()
        self._closed = False

    @property
    def run_id(self) -> str:
        return self._session["id"]

    # Back-compat alias
    @property
    def session_id(self) -> str:
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
    ) -> Step:
        return Step(
            self,
            action_type,
            input=input,
            output=output,
            metadata=metadata,
            custom_fields=custom_fields,
        )

    # ── Emit / flush ───────────────────────────────────────────────────

    def _emit(
        self,
        *,
        id: str,
        action_type: str,
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
            body = self._build_node_body(
                id=id,
                action_type=action_type,
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
            if not self._buffered or len(self._buffer) >= BATCH_MAX:
                self._flush_locked()

    def _build_node_body(
        self,
        *,
        id: str,
        action_type: str,
        input: Any | None,
        output: Any | None,
        error: Any | None,
        metadata: dict[str, Any] | None,
        custom_fields: dict[str, Any] | None,
        parent_id: str | None,
        timestamp: int | None,
        duration_ms: int | None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "run_id": self.run_id,
            "id": id,
            "action_type": action_type,
        }
        if input is not None:
            body["input"] = input
        if output is not None:
            body["output"] = output
        if error is not None:
            body["error"] = error
        if metadata is not None:
            body["metadata"] = metadata
        if custom_fields is not None:
            body["custom_fields"] = custom_fields
        if parent_id is not None:
            body["parent_id"] = parent_id
        if duration_ms is not None:
            body["duration_ms"] = duration_ms

        if self._signing_key:
            ts = timestamp if timestamp is not None else _now_ms()
            prev = [] if self._last_hash is None else [self._last_hash]
            payload = {
                "id": id,
                "run_id": self.run_id,
                "agent_id": self._session["agent_id"],
                "parent_id": parent_id,
                "action_type": action_type,
                "input": input,
                "output": output,
                "error": error,
                "metadata": metadata if metadata is not None else {},
                "custom_fields": custom_fields if custom_fields is not None else {},
                "timestamp": ts,
                "duration_ms": duration_ms,
                "previous_hashes": prev,
            }
            body["timestamp"] = ts
            body["previous_hashes"] = prev
            body["signature"] = sign_ed25519(hash_node_payload(payload), self._signing_key)
            # Pre-compute our own tail hash so the next signed node chains correctly.
            self._last_hash = hash_node_payload(payload)
        elif timestamp is not None:
            body["timestamp"] = timestamp
        return body

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

    # ── Low-level escape hatch ─────────────────────────────────────────

    def node(
        self,
        *,
        action_type: str,
        input: Any | None = None,
        output: Any | None = None,
        error: Any | None = None,
        metadata: dict[str, Any] | None = None,
        custom_fields: dict[str, Any] | None = None,
        timestamp: int | None = None,
        duration_ms: int | None = None,
        parent_id: str | None = None,
    ) -> dict[str, Any]:
        """Write a single node immediately, bypassing buffer.

        Prefer :meth:`step` for ergonomic multi-step flows. This method
        stays for callers that want raw control.
        """
        with self._lock:
            # Flush any buffered nodes first so ordering/chaining is preserved.
            self._flush_locked()
            body = self._build_node_body(
                id=_random_node_id(),
                action_type=action_type,
                input=input,
                output=output,
                error=error,
                metadata=metadata,
                custom_fields=custom_fields,
                parent_id=parent_id,
                timestamp=timestamp,
                duration_ms=duration_ms,
            )
            res = self._http.post("/v1/nodes", json=body)
            node = res["data"][0]
            if "hash" in node and not self._signing_key:
                self._last_hash = node["hash"]
            return node

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
    ) -> dict[str, Any]:
        params: dict[str, str] = {}
        if cursor:
            params["cursor"] = cursor
        if limit:
            params["limit"] = str(limit)
        qs = f"?{urlencode(params)}" if params else ""
        return self._http.get(f"/v1/runs{qs}")

    def get(self, id: str) -> Run:
        res = self._http.get(f"/v1/runs/{id}")
        return Run(self._http, res["run"], self._signing_key)
