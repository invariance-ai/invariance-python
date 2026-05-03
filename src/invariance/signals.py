"""Signals SDK surface.

Signals are the operational-event primitive: "what needs attention?".
Users declare a ``SignalType`` once and emit instances from inside a run
(attached to the most recent node) or via the top-level
``inv.signals.emit(...)`` resource.

>>> DangerousOutput = define_signal_type(
...     "dangerous_output",
...     severity="high",
...     title="Dangerous output",
... )
>>> with inv.runs.start(name="x") as run:
...     with run.step("tool.use") as s: s.output = {"answer": "..."}
...     run.signal(DangerousOutput.signal(data={"reason": "keyword"}))
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from ._types import Severity, Signal, SignalList, SignalSource, SignalStatus
from .client import HttpClient
from ._query import with_query

__all__ = [
    "Signal",
    "SignalSource",
    "SignalStatus",
    "SignalType",
    "SignalsResource",
    "build_signal_body",
    "define_signal_type",
]


def build_signal_body(
    *,
    severity: Severity | None = None,
    title: str,
    message: str | None = None,
    type: str | None = None,
    data: Any | None = None,
    node_id: str | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    """Assemble the POST body for /v1/signals, stripping unset fields.

    severity defaults to ``"info"`` when omitted.
    """
    body: dict[str, Any] = {"severity": severity or "info", "title": title}
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
    return body


@dataclass(frozen=True)
class SignalType:
    """A declared signal category.

    Pairs with the backend ``signals.type`` column and with monitor
    ``action.emit_signal(type=...)``. ``signal()`` stamps this type onto
    a signal body dict suitable for ``run.signal(...)`` or
    ``inv.signals.emit(**spec)``.
    """

    type: str
    severity: Severity
    title: str
    message: str | None = None

    def signal(
        self,
        *,
        data: Any | None = None,
        node_id: str | None = None,
        run_id: str | None = None,
        severity: Severity | None = None,
        title: str | None = None,
        message: str | None = None,
    ) -> dict[str, Any]:
        return build_signal_body(
            severity=severity or self.severity,
            title=title or self.title,
            message=message if message is not None else self.message,
            type=self.type,
            data=data,
            node_id=node_id,
            run_id=run_id,
        )


def define_signal_type(
    type: str,
    *,
    severity: Severity,
    title: str,
    message: str | None = None,
) -> SignalType:
    """Convenience factory mirroring the TS ``defineSignalType`` surface."""
    return SignalType(type=type, severity=severity, title=title, message=message)


class SignalsResource:
    def __init__(self, http: HttpClient) -> None:
        self._http = http

    def emit(
        self,
        *,
        title: str,
        severity: Severity | None = None,
        message: str | None = None,
        type: str | None = None,
        data: Any | None = None,
        node_id: str | None = None,
        run_id: str | None = None,
    ) -> Signal:
        """Emit a signal. ``severity`` defaults to ``"info"``.

        ``run_id`` / ``node_id`` fall back to the ``INVARIANCE_RUN_ID`` /
        ``INVARIANCE_NODE_ID`` env vars when unset, so coding agents
        running inside a recorded run can emit progress events without
        plumbing IDs explicitly.
        """
        import os

        body = build_signal_body(
            severity=severity,
            title=title,
            message=message,
            type=type,
            data=data,
            node_id=node_id if node_id is not None else os.environ.get("INVARIANCE_NODE_ID"),
            run_id=run_id if run_id is not None else os.environ.get("INVARIANCE_RUN_ID"),
        )
        res = self._http.post("/v1/signals", json=body)
        return res["signal"]

    def list(
        self,
        *,
        cursor: str | None = None,
        limit: int | None = None,
    ) -> SignalList:
        return self._http.get(with_query("/v1/signals", cursor=cursor, limit=limit))

    def get(self, id: str) -> Signal:
        res = self._http.get(f"/v1/signals/{id}")
        return res["signal"]

    def acknowledge(self, id: str) -> Signal:
        res = self._http.patch(f"/v1/signals/{id}/acknowledge")
        return res["signal"]

    def resolve(self, id: str) -> Signal:
        res = self._http.patch(f"/v1/signals/{id}/resolve")
        return res["signal"]
