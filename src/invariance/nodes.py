from __future__ import annotations

from typing import Any
from urllib.parse import urlencode

from ._types import Node, NodeList
from .client import HttpClient


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
        params: dict[str, str] = {}
        if cursor:
            params["cursor"] = cursor
        if limit:
            params["limit"] = str(limit)
        qs = f"?{urlencode(params)}" if params else ""
        return self._http.get(f"/v1/runs/{run_id}/nodes{qs}")
