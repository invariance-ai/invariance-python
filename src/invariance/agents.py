from __future__ import annotations

from typing import Any

from .client import HttpClient


class AgentsResource:
    def __init__(self, http: HttpClient) -> None:
        self._http = http

    def me(self) -> dict[str, Any]:
        return self._http.get("/v1/agents/me")
