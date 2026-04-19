"""Monitors SDK surface.

Mirror of the TypeScript ``monitors`` module. Users compose a
``MonitorSpec`` from builders (``on``, ``rule``, ``evaluator``,
``action``), and the resource compiles it to a backend
``MonitorDefinition`` JSON body before POSTing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal
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


# ── Spec dataclasses ───────────────────────────────────────────────────────


@dataclass
class MonitorSpec:
    name: str
    on: dict[str, Any]
    when: dict[str, Any]
    do: dict[str, Any] | list[dict[str, Any]]
    severity: Severity = "medium"
    description: str | None = None


# ── Builders ───────────────────────────────────────────────────────────────


class on:
    """Selector builders — compile to ``MonitorTargetMatch`` + trigger."""

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
    def field_equals(field: str, value: Any) -> dict[str, Any]:
        return {"_kind": "field_equals", "field": field, "value": value}

    @staticmethod
    def field_contains(field: str, value: Any) -> dict[str, Any]:
        return {"_kind": "field_contains", "field": field, "value": value}

    @staticmethod
    def numeric(field: str, op: NumericOp, value: float) -> dict[str, Any]:
        return {"_kind": "numeric", "field": field, "op": op, "value": value}

    @staticmethod
    def exists(field: str, exists: bool = True) -> dict[str, Any]:
        return {"_kind": "exists", "field": field, "exists": exists}

    @staticmethod
    def frequency(
        field: str,
        value: Any,
        *,
        per_minutes: int,
        op: NumericOp,
        threshold: float,
        window_minutes: int,
    ) -> dict[str, Any]:
        return {
            "_kind": "frequency",
            "field": field,
            "value": value,
            "per_minutes": per_minutes,
            "op": op,
            "threshold": threshold,
            "window_minutes": window_minutes,
        }

    @staticmethod
    def all_(*rules: dict[str, Any]) -> dict[str, Any]:
        return {"_match": "all", "rules": list(rules)}

    @staticmethod
    def any_(*rules: dict[str, Any]) -> dict[str, Any]:
        return {"_match": "any", "rules": list(rules)}


class evaluator:
    @staticmethod
    def judge_llm(
        *,
        model: str,
        rubric: str,
        output_schema: dict[str, Any] | None = None,
        max_tokens: int | None = None,
    ) -> dict[str, Any]:
        return {
            "_kind": "judge_llm",
            "model": model,
            "rubric": rubric,
            "output_schema": output_schema,
            "max_tokens": max_tokens,
        }

    @staticmethod
    def judge_human(
        *,
        queue: str,
        instructions: str | None = None,
        notify: list[Literal["email", "slack", "dashboard"]] | None = None,
    ) -> dict[str, Any]:
        return {"_kind": "judge_human", "queue": queue, "instructions": instructions, "notify": notify}

    @staticmethod
    def code(inline_script: str, *, runtime: Literal["hosted", "customer"] = "hosted") -> dict[str, Any]:
        return {"_kind": "code", "inline_script": inline_script, "runtime": runtime}


class action:
    @staticmethod
    def create_finding(
        *, severity: Severity, title: str, message: str | None = None, type: str | None = None
    ) -> dict[str, Any]:
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
    ) -> dict[str, Any]:
        return {
            "_kind": "emit_signal",
            "severity": severity,
            "title": title,
            "message": message,
            "type": type,
        }

    @staticmethod
    def notify(channel: Literal["email", "slack", "webhook", "dashboard"], target: str) -> dict[str, Any]:
        return {"_kind": "notify", "channel": channel, "target": target}

    @staticmethod
    def mark(label: str) -> dict[str, Any]:
        return {"_kind": "mark", "label": label}

    @staticmethod
    def webhook(
        url: str,
        *,
        method: Literal["GET", "POST"] = "POST",
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        return {"_kind": "webhook", "url": url, "method": method, "headers": headers}


# ── Compilation ────────────────────────────────────────────────────────────


_OP_MAP: dict[str, str] = {"gt": ">", "gte": ">=", "lt": "<", "lte": "<="}


def _compile_rule_to_evaluator(r: dict[str, Any]) -> dict[str, Any]:
    """Map a single SDK rule to a backend ``MonitorEvaluator``.

    Backend supports exactly two evaluator types: ``keyword`` (substring
    match) and ``threshold`` (numeric comparison). Other rule kinds
    (``exists``, ``frequency``, LLM/human/code judges, rule composition)
    are out of scope for the MVP backend and raise ``NotImplementedError``.
    """
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
    if kind in {"exists", "frequency"}:
        raise NotImplementedError(
            f"rule.{kind} is not supported by the current backend evaluator"
        )
    if kind in {"judge_llm", "judge_human", "code"}:
        raise NotImplementedError(
            f"evaluator.{kind} is not supported by the current backend evaluator"
        )
    raise ValueError(f"unknown rule kind: {kind}")


def compile_monitor(spec: MonitorSpec) -> dict[str, Any]:
    """Compile a :class:`MonitorSpec` to a backend ``CreateMonitorRequest``.

    Returned shape matches ``@invariance/api-types`` ``CreateMonitorRequest``:
    ``{name, description?, evaluator, severity, signal_type?, creates_review?, schedule?}``.

    Unsupported DSL constructs raise ``NotImplementedError`` with an
    explicit message so callers can see exactly which piece isn't wired
    through yet.
    """
    w = spec.when
    if "_match" in w:
        raise NotImplementedError(
            "rule.any_/all_ composition is not supported by the current backend evaluator"
        )
    evaluator_body = _compile_rule_to_evaluator(w)

    do_list = spec.do if isinstance(spec.do, list) else [spec.do]
    signal_action = next(
        (a for a in do_list if a.get("_kind") in {"emit_signal", "create_finding"}), None
    )
    signal_type: str | None = signal_action["type"] if signal_action and signal_action.get("type") else None
    creates_review = any(a.get("_kind") == "create_finding" for a in do_list)

    for a in do_list:
        if a.get("_kind") in {"notify", "mark", "webhook"}:
            raise NotImplementedError(
                f"action.{a['_kind']} is not supported by the current backend"
            )

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
