"""Captures — agent session recordings served at /v1/captures."""

from __future__ import annotations

from typing import Any

from .client import HttpClient
from ._query import with_query

# Sentinel for distinguishing "not passed" from explicit None in update().
_UNSET = object()


class CapturesResource:
    def __init__(self, http: HttpClient) -> None:
        self._http = http

    def create(
        self,
        *,
        source: str,
        session_type: str | None = None,
        title: str | None = None,
        external_session_id: str | None = None,
        model: str | None = None,
        cwd: str | None = None,
        client_version: str | None = None,
        run_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
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
        if run_id is not None:
            body["run_id"] = run_id
        if metadata is not None:
            body["metadata"] = metadata
        if tags is not None:
            body["tags"] = tags
        res = self._http.post("/v1/captures", json=body)
        return res["session"]

    def get(self, id: str) -> dict[str, Any]:
        res = self._http.get(f"/v1/captures/{id}")
        return res["session"]

    def list(
        self,
        *,
        project_id: str | None = None,
        operator_id: str | None = None,
        session_type: str | None = None,
        source: str | None = None,
        run_id: str | None = None,
        tags: str | None = None,
        cursor: str | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        return self._http.get(
            with_query(
                "/v1/captures",
                project_id=project_id,
                operator_id=operator_id,
                session_type=session_type,
                source=source,
                run_id=run_id,
                tags=tags,
                cursor=cursor,
                limit=limit,
            )
        )

    def update(
        self,
        id: str,
        *,
        run_id: object = _UNSET,
        status: str | None = None,
        agent_id: str | None = None,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {}
        if run_id is not _UNSET:
            body["run_id"] = run_id  # may be None (unlink) or a string (link)
        if status is not None:
            body["status"] = status
        if agent_id is not None:
            body["agent_id"] = agent_id
        if tags is not None:
            body["tags"] = tags
        res = self._http.patch(f"/v1/captures/{id}", json=body)
        return res["session"]

    def link(self, id: str, *, run_id: str) -> dict[str, Any]:
        res = self._http.patch(f"/v1/captures/{id}", json={"run_id": run_id})
        return res["session"]

    def unlink(self, id: str) -> dict[str, Any]:
        res = self._http.patch(f"/v1/captures/{id}", json={"run_id": None})
        return res["session"]

    def list_links(self, id: str) -> dict[str, Any]:
        capture = self.get(id)
        return {"run_id": capture.get("run_id")}
