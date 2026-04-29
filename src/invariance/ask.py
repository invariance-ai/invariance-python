from __future__ import annotations

from typing import Any

from ._types import AskResponse
from .client import HttpClient


class AskResource:
    def __init__(self, http: HttpClient) -> None:
        self._http = http

    def send(
        self,
        message: str,
        *,
        session_id: str | None = None,
        model: str | None = None,
        max_turns: int | None = None,
    ) -> AskResponse:
        payload: dict[str, Any] = {"message": message}
        if session_id is not None:
            payload["session_id"] = session_id
        if model is not None:
            payload["model"] = model
        if max_turns is not None:
            payload["max_turns"] = max_turns
        return self._http.post("/v1/ask", json=payload)
