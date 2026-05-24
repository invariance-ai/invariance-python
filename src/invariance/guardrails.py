"""Per-agent guardrail lifecycle.

Guardrails are created from recipes or findings; the canonical lifecycle
transition is ``promote(id, to=...)``: suggested → accepted → shadow →
active_monitor → rejected.
"""

from __future__ import annotations

from ._query import with_query
from ._types import Guardrail, GuardrailList, GuardrailMode, GuardrailStatus
from .client import HttpClient


class GuardrailsResource:
    def __init__(self, http: HttpClient) -> None:
        self._http = http

    def list(
        self,
        *,
        status: GuardrailStatus | None = None,
        recipe_id: str | None = None,
        cursor: str | None = None,
        limit: int | None = None,
    ) -> GuardrailList:
        return self._http.get(
            with_query(
                "/v1/guardrails",
                status=status,
                recipe_id=recipe_id,
                cursor=cursor,
                limit=limit,
            )
        )

    def get(self, id: str) -> Guardrail:
        res = self._http.get(f"/v1/guardrails/{id}")
        return res["guardrail"]

    def create(
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
        body: dict[str, object] = {"title": title}
        if recipe_id is not None:
            body["recipe_id"] = recipe_id
        if finding_id is not None:
            body["finding_id"] = finding_id
        if rule is not None:
            body["rule"] = rule
        if mode is not None:
            body["mode"] = mode
        if status is not None:
            body["status"] = status
        if agent_id is not None:
            body["agent_id"] = agent_id
        res = self._http.post("/v1/guardrails", json=body)
        return res["guardrail"]

    def update(
        self,
        id: str,
        *,
        mode: GuardrailMode | None = None,
        status: GuardrailStatus | None = None,
        monitor_id: str | None = None,
    ) -> Guardrail:
        patch: dict[str, object] = {}
        if mode is not None:
            patch["mode"] = mode
        if status is not None:
            patch["status"] = status
        if monitor_id is not None:
            patch["monitor_id"] = monitor_id
        res = self._http.request("PATCH", f"/v1/guardrails/{id}", json=patch)
        return res["guardrail"]

    def promote(self, id: str, *, to: GuardrailStatus) -> Guardrail:
        res = self._http.post(f"/v1/guardrails/{id}/promote", json={"to": to})
        return res["guardrail"]
