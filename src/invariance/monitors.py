"""Monitors SDK surface.

Mirror of the TypeScript ``monitors`` module. Users compose a
``MonitorSpec`` from builders (``on``, ``rule``, ``evaluator``,
``action``), and the resource compiles it to a backend
``MonitorDefinition`` JSON body before POSTing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal
from urllib.parse import urlencode

from .client import HttpClient


Severity = Literal["info", "low", "medium", "high", "critical"]
NumericOp = Literal["gt", "gte", "lt", "lte"]


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
    def create_finding(*, severity: Severity, title: str, message: str | None = None) -> dict[str, Any]:
        return {"_kind": "create_finding", "severity": severity, "title": title, "message": message}

    @staticmethod
    def emit_signal(*, severity: Severity, title: str, message: str | None = None) -> dict[str, Any]:
        return {"_kind": "emit_signal", "severity": severity, "title": title, "message": message}

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


def _compile_on(o: dict[str, Any]) -> dict[str, Any]:
    scope = o["_scope"]
    if scope == "session":
        filters = []
        if o.get("id"):
            filters.append({"field": "session_id", "operator": "eq", "value": o["id"]})
        target_match: dict[str, Any] = {"mode": "direct", "scope": "session", "filters": filters}
        if o.get("tags"):
            target_match["labels"] = o["tags"]
        return {
            "target": "session",
            "target_match": target_match,
            "trigger": {"type": "event", "source": "session"},
        }
    if scope == "run":
        filters = []
        if o.get("id"):
            filters.append({"field": "run_id", "operator": "eq", "value": o["id"]})
        if o.get("agent_id"):
            filters.append({"field": "agent_id", "operator": "eq", "value": o["agent_id"]})
        return {
            "target": "trace_node",
            "target_match": {"mode": "contains", "scope": "run", "filters": filters},
            "trigger": {"type": "event", "source": "trace_node"},
        }
    if scope == "agent":
        return {
            "target": "trace_node",
            "target_match": {
                "mode": "contains",
                "scope": "agent",
                "filters": [{"field": "agent_id", "operator": "eq", "value": o["id"]}],
            },
            "trigger": {"type": "event", "source": "trace_node"},
        }
    if scope == "node":
        filters = []
        if o.get("type"):
            filters.append({"field": "type", "operator": "eq", "value": o["type"]})
        if o.get("action_type"):
            filters.append({"field": "action_type", "operator": "eq", "value": o["action_type"]})
        if o.get("agent_id"):
            filters.append({"field": "agent_id", "operator": "eq", "value": o["agent_id"]})
        return {
            "target": "trace_node",
            "target_match": {"mode": "direct", "scope": "node", "filters": filters},
            "trigger": {"type": "event", "source": "trace_node"},
        }
    # batch
    return {
        "target": "signal",
        "target_match": {"mode": "contains", "scope": "batch"},
        "trigger": {"type": "schedule", "cadence_minutes": o["window_minutes"]},
    }


def _compile_rule(r: dict[str, Any]) -> dict[str, Any]:
    kind = r["_kind"]
    if kind == "field_equals":
        return {"kind": "field_match", "field": r["field"], "operator": "eq", "value": r["value"]}
    if kind == "field_contains":
        return {"kind": "field_match", "field": r["field"], "operator": "contains", "value": r["value"]}
    if kind == "numeric":
        return {"kind": "numeric_threshold", "field": r["field"], "operator": r["op"], "value": r["value"]}
    if kind == "exists":
        return {"kind": "exists", "field": r["field"], "exists": r["exists"]}
    if kind == "frequency":
        return {
            "kind": "frequency",
            "field": r["field"],
            "operator": "eq",
            "value": r["value"],
            "rate": {"per_minutes": r["per_minutes"], "operator": r["op"], "value": r["threshold"]},
            "window_minutes": r["window_minutes"],
        }
    raise ValueError(f"unknown rule kind: {kind}")


def _compile_evaluator(e: dict[str, Any]) -> dict[str, Any]:
    kind = e["_kind"]
    if kind == "judge_llm":
        return {
            "type": "judge_llm",
            "model": e["model"],
            "rubric": e["rubric"],
            "output_schema": e["output_schema"],
            "max_tokens": e["max_tokens"],
        }
    if kind == "judge_human":
        return {"type": "judge_human", "queue": e["queue"], "instructions": e["instructions"], "notify": e["notify"]}
    if kind == "code":
        return {"type": "code", "runtime": e["runtime"], "entrypoint": "main", "inline_script": e["inline_script"]}
    raise ValueError(f"unknown evaluator kind: {kind}")


def _compile_action(a: dict[str, Any]) -> dict[str, Any]:
    kind = a["_kind"]
    if kind == "create_finding":
        return {"type": "create_finding", "severity": a["severity"], "title": a["title"], "message": a["message"] or a["title"]}
    if kind == "emit_signal":
        return {"type": "emit_signal", "severity": a["severity"], "title": a["title"], "message": a["message"] or a["title"]}
    if kind == "notify":
        return {"type": "notify", "channel": a["channel"], "target": a["target"]}
    if kind == "mark":
        return {"type": "mark_object", "label": a["label"]}
    if kind == "webhook":
        return {"type": "webhook", "url": a["url"], "method": a["method"], "headers": a["headers"]}
    raise ValueError(f"unknown action kind: {kind}")


_EVALUATOR_KINDS = {"judge_llm", "judge_human", "code"}


def compile_monitor(spec: MonitorSpec) -> dict[str, Any]:
    target_bits = _compile_on(spec.on)
    do_list = spec.do if isinstance(spec.do, list) else [spec.do]
    actions = [_compile_action(a) for a in do_list]

    match: Literal["all", "any"] = "all"
    rules: list[dict[str, Any]] = []
    evaluator_def: dict[str, Any] | None = None

    w = spec.when
    if "_kind" in w and w["_kind"] in _EVALUATOR_KINDS:
        evaluator_def = _compile_evaluator(w)
    elif "_kind" in w:
        rules = [_compile_rule(w)]
    elif "_match" in w:
        match = w["_match"]
        rules = [_compile_rule(r) for r in w["rules"]]
    else:
        raise ValueError("invalid 'when' expression")

    signal_action = next((a for a in actions if a["type"] in ("create_finding", "emit_signal")), None)
    signal = (
        {"title": signal_action["title"], "message": signal_action["message"], "severity": signal_action["severity"]}
        if signal_action
        else {"title": spec.name, "message": spec.description or spec.name, "severity": spec.severity}
    )

    definition: dict[str, Any] = {
        "version": 1,
        "target": target_bits["target"],
        "target_match": target_bits["target_match"],
        "match": match,
        "rules": rules,
        "actions": actions,
        "signal": signal,
        "trigger": target_bits["trigger"],
    }
    if evaluator_def is not None:
        definition["evaluator"] = evaluator_def
    return definition


# ── Resources ──────────────────────────────────────────────────────────────


class MonitorsResource:
    def __init__(self, http: HttpClient) -> None:
        self._http = http

    def create(self, spec: MonitorSpec) -> dict[str, Any]:
        body = {"name": spec.name, "definition": compile_monitor(spec), "severity": spec.severity}
        res = self._http.post("/v1/monitors", json=body)
        return res["monitor"]

    def get(self, id: str) -> dict[str, Any]:
        res = self._http.get(f"/v1/monitors/{id}")
        return res["monitor"]

    def list(
        self,
        *,
        cursor: str | None = None,
        limit: int | None = None,
        status: Literal["active", "paused", "disabled"] | None = None,
    ) -> dict[str, Any]:
        params: dict[str, str] = {}
        if cursor:
            params["cursor"] = cursor
        if limit:
            params["limit"] = str(limit)
        if status:
            params["status"] = status
        qs = f"?{urlencode(params)}" if params else ""
        return self._http.get(f"/v1/monitors{qs}")

    def update(
        self,
        id: str,
        *,
        name: str | None = None,
        severity: Severity | None = None,
        status: Literal["active", "paused"] | None = None,
    ) -> dict[str, Any]:
        patch: dict[str, Any] = {}
        if name is not None:
            patch["name"] = name
        if severity is not None:
            patch["severity"] = severity
        if status is not None:
            patch["status"] = status
        res = self._http.request("PUT", f"/v1/monitors/{id}", json=patch)
        return res["monitor"]

    def pause(self, id: str) -> dict[str, Any]:
        return self.update(id, status="paused")

    def resume(self, id: str) -> dict[str, Any]:
        return self.update(id, status="active")
