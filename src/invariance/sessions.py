"""Agent sessions — units of work attached to an operator.

A session is a coding stint, a meeting, a note, or a recording. The ``from_*``
helpers normalize the source/session_type combo for common ingestion paths;
they do not parse the underlying transcript. Pass events to
:meth:`SessionsResource.append_events` separately.
"""

from __future__ import annotations

from typing import Any

from ._query import with_query
from ._types import (
    AgentSession,
    AgentSessionList,
    AgentSessionSource,
    AgentSessionType,
    AppendEventsResponse,
    CreateAgentSessionResponse,
)
from .client import HttpClient


class SessionsResource:
    def __init__(self, http: HttpClient) -> None:
        self._http = http

    def create(
        self,
        *,
        source: AgentSessionSource,
        session_type: AgentSessionType | None = None,
        title: str | None = None,
        external_session_id: str | None = None,
        model: str | None = None,
        cwd: str | None = None,
        client_version: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AgentSession:
        body: dict[str, Any] = {"source": source}
        if session_type is not None:
            body["session_type"] = session_type
        if title is not None:
            body["title"] = title
        if external_session_id is not None:
            body["external_session_id"] = external_session_id
        if model is not None:
            body["model"] = model
        if cwd is not None:
            body["cwd"] = cwd
        if client_version is not None:
            body["client_version"] = client_version
        if metadata is not None:
            body["metadata"] = metadata
        res: CreateAgentSessionResponse = self._http.post(
            "/v1/agent-sessions", json=body
        )
        return res["session"]

    def list(
        self,
        *,
        project_id: str | None = None,
        operator_id: str | None = None,
        session_type: AgentSessionType | None = None,
        source: AgentSessionSource | None = None,
        cursor: str | None = None,
        limit: int | None = None,
    ) -> AgentSessionList:
        return self._http.get(
            with_query(
                "/v1/agent-sessions",
                project_id=project_id,
                operator_id=operator_id,
                session_type=session_type,
                source=source,
                cursor=cursor,
                limit=limit,
            )
        )

    def get(self, id: str) -> AgentSession:
        res = self._http.get(f"/v1/agent-sessions/{id}")
        return res["session"]

    def append_events(
        self, id: str, events: list[dict[str, Any]]
    ) -> AppendEventsResponse:
        return self._http.post(
            f"/v1/agent-sessions/{id}/events", json={"events": events}
        )

    # ── Ergonomic wrappers ────────────────────────────────────────────────

    def from_claude_code(self, **kwargs: Any) -> AgentSession:
        kwargs.setdefault("source", "claude_code")
        kwargs.setdefault("session_type", "coding")
        return self.create(**kwargs)

    def from_meeting_notes(self, **kwargs: Any) -> AgentSession:
        kwargs.setdefault("source", "meeting")
        kwargs.setdefault("session_type", "meeting")
        return self.create(**kwargs)

    def from_granola_note(self, **kwargs: Any) -> AgentSession:
        kwargs.setdefault("source", "granola_note")
        kwargs.setdefault("session_type", "note")
        return self.create(**kwargs)
