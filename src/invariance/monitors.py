"""Monitors SDK surface.

Mirror of the TypeScript ``monitors`` module. Users compose a
``MonitorSpec`` from builders (``on``, ``rule``, ``action``), and the
resource compiles it to the platform's ``CreateMonitorRequest`` JSON
body before POSTing.

The DSL is deliberately scoped to exactly what the platform backend
supports: keyword and threshold evaluators, with ``emit_signal`` /
``create_finding`` actions.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Union
from urllib.parse import urlencode

from ._types import (
    EvaluateMonitorResponse,
    FindingList,
    Monitor,
    MonitorExecutionList,
    MonitorList,
    NumericOp,
    Severity,
)
from .client import HttpClient


# ── Rule / Action shapes ───────────────────────────────────────────────────


Rule = dict[str, Any]
Action = dict[str, Any]


@dataclass
class MonitorSpec:
    name: str
    on: dict[str, Any]
    when: Rule
    do: Union[Action, list[Action]]
    severity: Severity = "medium"
    description: str | None = None


# ── Builders ───────────────────────────────────────────────────────────────


class on:
    """Selector hints. The platform currently scopes evaluation per
    agent; these remain as ergonomic metadata that may influence future
    filtering. They do not change the compiled ``CreateMonitorRequest``.
    """

    @staticmethod
    def session(*, id: str | None = None, tags: list[str] | None = None) -> dict[str, Any]:
        return {"_scope": "session", "id": id, "tags": tags}

    @staticmethod
    def run(*, id: str | None = None, agent_id: str | None = None) -> dict[str, Any]:
        return {"_scope": "run", "id": id, "agent_id": agent_id}

    @staticmethod
    def agent(id: str) -> dict[str, Any]:
        return {"_scope": "agent", "id": id}

    @staticmethod
    def node(
        *,
        type: str | None = None,
        action_type: str | None = None,
        agent_id: str | None = None,
    ) -> dict[str, Any]:
        return {"_scope": "node", "type": type, "action_type": action_type, "agent_id": agent_id}

    @staticmethod
    def batch(window_minutes: int) -> dict[str, Any]:
        return {"_scope": "batch", "window_minutes": window_minutes}


class rule:
    @staticmethod
    def field_equals(field: str, value: Any) -> Rule:
        return {"_kind": "field_equals", "field": field, "value": value}

    @staticmethod
    def field_contains(field: str, value: Any) -> Rule:
        return {"_kind": "field_contains", "field": field, "value": value}

    @staticmethod
    def numeric(field: str, op: NumericOp, value: float) -> Rule:
        return {"_kind": "numeric", "field": field, "op": op, "value": value}


class action:
    @staticmethod
    def create_finding(
        *, severity: Severity, title: str, message: str | None = None, type: str | None = None
    ) -> Action:
        return {
            "_kind": "create_finding",
            "severity": severity,
            "title": title,
            "message": message,
            "type": type,
        }

    @staticmethod
    def emit_signal(
        *, severity: Severity, title: str, message: str | None = None, type: str | None = None
    ) -> Action:
        return {
            "_kind": "emit_signal",
            "severity": severity,
            "title": title,
            "message": message,
            "type": type,
        }


# ── Compilation ────────────────────────────────────────────────────────────


_OP_MAP: dict[str, str] = {
    "gt": ">",
    "gte": ">=",
    "lt": "<",
    "lte": "<=",
    "eq": "==",
    "neq": "!=",
}


def _compile_rule_to_evaluator(r: Rule) -> dict[str, Any]:
    kind = r.get("_kind")
    if kind == "field_contains":
        return {
            "type": "keyword",
            "field": r["field"],
            "keywords": [r["value"]],
            "case_sensitive": False,
        }
    if kind == "field_equals":
        return {
            "type": "keyword",
            "field": r["field"],
            "keywords": [str(r["value"])],
            "case_sensitive": True,
        }
    if kind == "numeric":
        return {
            "type": "threshold",
            "field": r["field"],
            "operator": _OP_MAP[r["op"]],
            "value": r["value"],
        }
    raise ValueError(f"unknown rule kind: {kind}")


def compile_monitor(spec: MonitorSpec) -> dict[str, Any]:
    """Compile a :class:`MonitorSpec` to a platform ``CreateMonitorRequest``.

    Returned shape matches ``@invariance/api-types`` ``CreateMonitorRequest``:
    ``{name, description?, evaluator, severity, signal_type?, creates_review?}``.
    """
    evaluator_body = _compile_rule_to_evaluator(spec.when)

    do_list = spec.do if isinstance(spec.do, list) else [spec.do]
    signal_action = next(
        (a for a in do_list if a.get("_kind") in {"emit_signal", "create_finding"}), None
    )
    signal_type: str | None = (
        signal_action["type"] if signal_action and signal_action.get("type") else None
    )
    creates_review = any(a.get("_kind") == "create_finding" for a in do_list)

    body: dict[str, Any] = {
        "name": spec.name,
        "evaluator": evaluator_body,
        "severity": signal_action["severity"] if signal_action else spec.severity,
    }
    if spec.description is not None:
        body["description"] = spec.description
    if signal_type is not None:
        body["signal_type"] = signal_type
    if creates_review:
        body["creates_review"] = True
    return body


# ── Resources ──────────────────────────────────────────────────────────────


class MonitorsResource:
    def __init__(self, http: HttpClient) -> None:
        self._http = http

    def create(self, spec: MonitorSpec) -> Monitor:
        res = self._http.post("/v1/monitors", json=compile_monitor(spec))
        return res["monitor"]

    def get(self, id: str) -> Monitor:
        res = self._http.get(f"/v1/monitors/{id}")
        return res["monitor"]

    def list(
        self,
        *,
        cursor: str | None = None,
        limit: int | None = None,
    ) -> MonitorList:
        params: dict[str, str] = {}
        if cursor:
            params["cursor"] = cursor
        if limit:
            params["limit"] = str(limit)
        qs = f"?{urlencode(params)}" if params else ""
        return self._http.get(f"/v1/monitors{qs}")

    def update(
        self,
        id: str,
        *,
        name: str | None = None,
        description: str | None = None,
        enabled: bool | None = None,
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
        if evaluator is not None:
            patch["evaluator"] = evaluator
        if schedule is not None:
            patch["schedule"] = schedule
        if creates_review is not None:
            patch["creates_review"] = creates_review
        if signal_type is not None:
            patch["signal_type"] = signal_type
        res = self._http.patch(f"/v1/monitors/{id}", json=patch)
        return res["monitor"]

    def pause(self, id: str) -> Monitor:
        return self.update(id, enabled=False)

    def resume(self, id: str) -> Monitor:
        return self.update(id, enabled=True)

    def evaluate(
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
        return self._http.post(f"/v1/monitors/{id}/evaluate", json=body)

    def executions(
        self,
        id: str,
        *,
        cursor: str | None = None,
        limit: int | None = None,
    ) -> MonitorExecutionList:
        params: dict[str, str] = {}
        if cursor:
            params["cursor"] = cursor
        if limit:
            params["limit"] = str(limit)
        qs = f"?{urlencode(params)}" if params else ""
        return self._http.get(f"/v1/monitors/{id}/executions{qs}")

    def findings(
        self,
        id: str,
        *,
        cursor: str | None = None,
        limit: int | None = None,
    ) -> FindingList:
        params: dict[str, str] = {}
        if cursor:
            params["cursor"] = cursor
        if limit:
            params["limit"] = str(limit)
        qs = f"?{urlencode(params)}" if params else ""
        return self._http.get(f"/v1/monitors/{id}/findings{qs}")
