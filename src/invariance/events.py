"""Workflow events — semantic facts over case/run/node evidence."""

from __future__ import annotations

from typing import Any

from ._query import with_query
from ._types import WorkflowEventActorType, WorkflowEventList
from .client import HttpClient


class EventsResource:
    def __init__(self, http: HttpClient) -> None:
        self._http = http

    def list(
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
        params = {
            "case_id": case_id,
            "tenant_id": tenant_id,
            "end_user_id": end_user_id,
            "workflow_key": workflow_key,
            "type": type,
            "actor_type": actor_type,
            "actor_id": actor_id,
            "from": from_,
            "to": to,
            "cursor": cursor,
            "limit": limit,
        }
        return self._http.get(
            with_query(
                "/v1/events",
                **params,
            )
        )

    def list_for_case(
        self,
        case_id: str,
        *,
        cursor: str | None = None,
        limit: int | None = None,
    ) -> WorkflowEventList:
        return self._http.get(
            with_query(f"/v1/cases/{case_id}/events", cursor=cursor, limit=limit)
        )

    def create(
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
        if actor_type is not None:
            body["actor_type"] = actor_type
        if actor_id is not None:
            body["actor_id"] = actor_id
        if payload is not None:
            body["payload"] = payload
        if evidence_node_ids is not None:
            body["evidence_node_ids"] = evidence_node_ids
        if evidence_refs is not None:
            body["evidence_refs"] = evidence_refs
        if idempotency_key is not None:
            body["idempotency_key"] = idempotency_key
        if occurred_at is not None:
            body["occurred_at"] = occurred_at
        res = self._http.post(f"/v1/cases/{case_id}/events", json=body)
        return res["event"]
