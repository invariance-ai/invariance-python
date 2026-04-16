from __future__ import annotations

from typing import Any
from urllib.parse import urlencode

from .client import HttpClient


class Run:
    """Wraps a backend session as a developer-facing Run."""

    def __init__(self, http: HttpClient, session: dict[str, Any]) -> None:
        self._http = http
        self._session = session

    @property
    def session_id(self) -> str:
        return self._session["id"]

    @property
    def name(self) -> str:
        return self._session["name"]

    @property
    def status(self) -> str:
        return self._session["status"]

    def node(
        self,
        *,
        action_type: str,
        input: Any | None = None,
        output: Any | None = None,
        error: Any | None = None,
        metadata: dict[str, Any] | None = None,
        timestamp: int | None = None,
        duration_ms: int | None = None,
        parent_id: str | None = None,
    ) -> dict[str, Any]:
        event: dict[str, Any] = {
            "session_id": self.session_id,
            "action_type": action_type,
        }
        if input is not None:
            event["input"] = input
        if output is not None:
            event["output"] = output
        if error is not None:
            event["error"] = error
        if metadata is not None:
            event["metadata"] = metadata
        if timestamp is not None:
            event["timestamp"] = timestamp
        if duration_ms is not None:
            event["duration_ms"] = duration_ms
        if parent_id is not None:
            event["parent_id"] = parent_id

        res = self._http.post("/v1/trace/events", json=event)
        return res["data"][0]

    def verify(self) -> dict[str, Any]:
        return self._http.get(f"/v1/sessions/{self.session_id}/verify")

    def finish(self) -> dict[str, Any]:
        res = self._http.patch(
            f"/v1/sessions/{self.session_id}",
            json={"status": "completed"},
        )
        return res["session"]

    def fail(self, error: str | None = None) -> dict[str, Any]:
        body: dict[str, Any] = {"status": "failed"}
        if error:
            body["metadata"] = {"error": error}
        res = self._http.patch(f"/v1/sessions/{self.session_id}", json=body)
        return res["session"]


class RunsResource:
    def __init__(self, http: HttpClient) -> None:
        self._http = http

    def start(
        self,
        name: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Run:
        body: dict[str, Any] = {}
        if name is not None:
            body["name"] = name
        if metadata is not None:
            body["metadata"] = metadata
        res = self._http.post("/v1/sessions", json=body)
        return Run(self._http, res["session"])

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
        return self._http.get(f"/v1/sessions{qs}")

    def get(self, id: str) -> Run:
        res = self._http.get(f"/v1/sessions/{id}")
        return Run(self._http, res["session"])
