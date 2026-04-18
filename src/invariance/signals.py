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
from urllib.parse import urlencode

from .client import HttpClient

Severity = Literal["info", "low", "medium", "high", "critical"]


@dataclass(frozen=True)
class SignalType:
    """A declared signal category.

    Pairs with the backend `signals.type` column and with monitor
    ``action.emit_signal(type=...)``. ``signal()`` stamps this type onto
    an :class:`EmitSignalInput` dict.
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
        body: dict[str, Any] = {
            "type": self.type,
            "severity": severity or self.severity,
            "title": title or self.title,
        }
        msg = message if message is not None else self.message
        if msg is not None:
            body["message"] = msg
        if data is not None:
            body["data"] = data
        if node_id is not None:
            body["node_id"] = node_id
        if run_id is not None:
            body["run_id"] = run_id
        return body


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
        severity: Severity,
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
        res = self._http.post("/v1/signals", json=body)
        return res["signal"]

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
        return self._http.get(f"/v1/signals{qs}")

    def get(self, id: str) -> dict[str, Any]:
        res = self._http.get(f"/v1/signals/{id}")
        return res["signal"]

    def acknowledge(self, id: str) -> dict[str, Any]:
        res = self._http.patch(f"/v1/signals/{id}/acknowledge")
        return res["signal"]
