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

    def link(
        self,
        id: str,
        *,
        run_id: str | None = None,
        target_type: str | None = None,
        target_id: str | None = None,
        link_type: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Link a capture to an evidence-graph target.

        Two forms:
        - ``run_id=...`` (legacy): sets the capture's run_id via PATCH and
          returns the updated capture.
        - ``target_id=...``: creates a capture link via POST
          ``/v1/captures/:id/links`` and returns the created link. ``target_type``
          defaults to ``"run"``, so passing only ``target_id`` links to a run.
        """
        if target_id is not None:
            body: dict[str, Any] = {
                "target_type": target_type or "run",
                "target_id": target_id,
            }
            if link_type is not None:
                body["link_type"] = link_type
            if metadata is not None:
                body["metadata"] = metadata
            res = self._http.post(f"/v1/captures/{id}/links", json=body)
            return res["link"]
        if run_id is None:
            raise ValueError("link() requires either run_id or target_id")
        res = self._http.patch(f"/v1/captures/{id}", json={"run_id": run_id})
        return res["session"]

    def unlink(self, id: str, *, link_id: str | None = None) -> dict[str, Any] | None:
        """Detach a capture from a target.

        With ``link_id`` deletes a specific evidence link; otherwise clears the
        capture's run_id via PATCH (legacy) and returns the updated capture.
        """
        if link_id is not None:
            self._http.delete(f"/v1/captures/{id}/links/{link_id}")
            return None
        res = self._http.patch(f"/v1/captures/{id}", json={"run_id": None})
        return res["session"]

    def list_links(self, id: str) -> dict[str, Any]:
        """List every evidence link on a capture (case/run/event/node)."""
        res = self._http.get(f"/v1/captures/{id}/links")
        links = res.get("links", [])
        run_id = next((l["run_id"] for l in links if l.get("run_id")), None)
        return {"links": links, "run_id": run_id}
