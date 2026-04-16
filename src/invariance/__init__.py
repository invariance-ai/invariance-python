from __future__ import annotations

from .client import HttpClient, InvarianceApiError
from .runs import Run, RunsResource
from .nodes import NodesResource
from .agents import AgentsResource

DEFAULT_API_URL = "https://api.invariance.dev"

__all__ = [
    "Invariance",
    "InvarianceApiError",
    "Run",
    "RunsResource",
    "NodesResource",
    "AgentsResource",
]


class Invariance:
    def __init__(self, api_key: str, api_url: str | None = None) -> None:
        if not api_key:
            raise ValueError("api_key is required")
        self._http = HttpClient(api_url or DEFAULT_API_URL, api_key)
        self.runs = RunsResource(self._http)
        self.nodes = NodesResource(self._http)
        self.agents = AgentsResource(self._http)

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> Invariance:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()
