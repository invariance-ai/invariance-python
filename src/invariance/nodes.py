from __future__ import annotations

from typing import Any

from ._types import Node, NodeList
from .client import HttpClient
from ._query import with_query


class NodesResource:
    def __init__(self, http: HttpClient) -> None:
        self._http = http

    def write(
        self,
        run_id: str,
        nodes: list[dict[str, Any]],
    ) -> list[Node]:
        body = [{"run_id": run_id, **n} for n in nodes]
        res = self._http.post("/v1/nodes", json=body)
        return res["data"]

    def list(
        self,
        run_id: str,
        *,
        cursor: str | None = None,
        limit: int | None = None,
    ) -> NodeList:
        return self._http.get(with_query(f"/v1/runs/{run_id}/nodes", cursor=cursor, limit=limit))
