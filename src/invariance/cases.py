"""Cases — workflow instances owning many runs across time, agents, and humans.

A Case is the unit of meaning for vertical AI-native platforms (one loan,
one audit, one claim). Single-agent users can ignore cases entirely; all
case fields are optional.

Use ``cases.with_case(case_or_id)`` as a context manager so any
``inv.runs.start(...)`` inside the block auto-stamps ``case_id`` +
``tenant_id`` + ``end_user_id`` — no need to thread the id through callers.

Example::

    c = inv.cases.create(workflow_key="mortgage.refi", tenant_id="acme")
    with inv.cases.with_case(c):
        run = inv.runs.start(name="underwrite")
        # run.case_id, run.tenant_id, run.end_user_id auto-stamped
        ...
        run.finish()
    inv.cases.close(c["id"], outcome="approved", value_usd=12_500)
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Iterator, Literal

from ._query import with_query
from ._types import WorkflowEventActorType, WorkflowEventList
from .client import HttpClient

CaseStatus = Literal["open", "closed"]


# Active case context — read by RunsResource.start to auto-stamp dimensions
# on runs created inside ``with_case(...)``. ContextVar is asyncio-safe; this
# is the Python analog to the TS SDK's AsyncLocalStorage.
_current_case: ContextVar["_CaseContext | None"] = ContextVar(
    "_current_case", default=None
)


class _CaseContext:
    __slots__ = ("case_id", "tenant_id", "end_user_id")

    def __init__(
        self,
        case_id: str,
        tenant_id: str | None,
        end_user_id: str | None,
    ) -> None:
        self.case_id = case_id
        self.tenant_id = tenant_id
        self.end_user_id = end_user_id


def active_case_context() -> _CaseContext | None:
    """Internal: returns the active case context (if any).

    RunsResource.start reads this to auto-stamp case_id/tenant_id/end_user_id
    onto runs created inside ``with cases.with_case(...)``.
    """
    return _current_case.get()


class CasesResource:
    def __init__(self, http: HttpClient) -> None:
        self._http = http

    def create(
        self,
        *,
        workflow_key: str,
        id: str | None = None,
        tenant_id: str | None = None,
        end_user_id: str | None = None,
        owner: str | None = None,
        custom_attrs: dict[str, Any] | None = None,
        opened_at: str | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"workflow_key": workflow_key}
        if id is not None:
            body["id"] = id
        if tenant_id is not None:
            body["tenant_id"] = tenant_id
        if end_user_id is not None:
            body["end_user_id"] = end_user_id
        if owner is not None:
            body["owner"] = owner
        if custom_attrs is not None:
            body["custom_attrs"] = custom_attrs
        if opened_at is not None:
            body["opened_at"] = opened_at
        res = self._http.post("/v1/cases", json=body)
        return res["case"]

    def get(self, id: str) -> dict[str, Any]:
        """Fetch a case with its linked runs (newest first, capped server-side)."""
        res = self._http.get(f"/v1/cases/{id}")
        return res["case"]

    def evidence(self, id: str) -> dict[str, Any]:
        """Fetch normalized case evidence: runs, nodes, events, actors, and outcome."""
        return self._http.get(f"/v1/cases/{id}/evidence")

    def list_events(
        self,
        id: str,
        *,
        cursor: str | None = None,
        limit: int | None = None,
    ) -> WorkflowEventList:
        return self._http.get(
            with_query(f"/v1/cases/{id}/events", cursor=cursor, limit=limit)
        )

    def create_event(
        self,
        id: str,
        *,
        type: str,
        actor_type: WorkflowEventActorType | None = None,
        actor_id: str | None = None,
        payload: dict[str, Any] | None = None,
        evidence_node_ids: list[str] | None = None,
        evidence_refs: list[dict[str, Any]] | None = None,
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
        if occurred_at is not None:
            body["occurred_at"] = occurred_at
        res = self._http.post(f"/v1/cases/{id}/events", json=body)
        return res["event"]

    def list(
        self,
        *,
        tenant_id: str | None = None,
        end_user_id: str | None = None,
        workflow_key: str | None = None,
        status: CaseStatus | None = None,
        outcome: str | None = None,
        cursor: str | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        return self._http.get(
            with_query(
                "/v1/cases",
                tenant_id=tenant_id,
                end_user_id=end_user_id,
                workflow_key=workflow_key,
                status=status,
                outcome=outcome,
                cursor=cursor,
                limit=limit,
            )
        )

    def update(
        self,
        id: str,
        *,
        status: CaseStatus | None = None,
        outcome: str | None = None,
        outcome_value_usd: float | None = None,
        owner: str | None = None,
        custom_attrs: dict[str, Any] | None = None,
        closed_at: str | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {}
        if status is not None:
            body["status"] = status
        if outcome is not None:
            body["outcome"] = outcome
        if outcome_value_usd is not None:
            body["outcome_value_usd"] = outcome_value_usd
        if owner is not None:
            body["owner"] = owner
        if custom_attrs is not None:
            body["custom_attrs"] = custom_attrs
        if closed_at is not None:
            body["closed_at"] = closed_at
        res = self._http.patch(f"/v1/cases/{id}", json=body)
        return res["case"]

    def close(
        self,
        id: str,
        *,
        outcome: str,
        value_usd: float | None = None,
        closed_at: str | None = None,
    ) -> dict[str, Any]:
        """Convenience: status='closed' + outcome in one call."""
        return self.update(
            id,
            status="closed",
            outcome=outcome,
            outcome_value_usd=value_usd,
            closed_at=closed_at,
        )

    @contextmanager
    def with_case(self, case_or_id: dict[str, Any] | str) -> Iterator[None]:
        """Run a block with a case context active.

        Any ``inv.runs.start(...)`` (sync) inside the ``with`` block is
        auto-stamped with ``case_id`` + ``tenant_id`` + ``end_user_id`` from
        this case.
        """
        if isinstance(case_or_id, str):
            c = self.get(case_or_id)
        else:
            c = case_or_id
        ctx = _CaseContext(
            case_id=c["id"],
            tenant_id=c.get("tenant_id"),
            end_user_id=c.get("end_user_id"),
        )
        token = _current_case.set(ctx)
        try:
            yield
        finally:
            _current_case.reset(token)
