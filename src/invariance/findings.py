"""Findings — high-level incidents created by monitors.

A Finding is the stable, reviewable record of "this monitor fired on
this node/run, here's what and why". Findings can be resolved or
dismissed; reviews attach to findings when ``monitor.creates_review``.
"""

from __future__ import annotations

from typing import Any, Literal
from urllib.parse import urlencode

from .client import HttpClient


FindingStatus = Literal["open", "review_requested", "resolved", "dismissed"]


class FindingsResource:
    def __init__(self, http: HttpClient) -> None:
        self._http = http

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
        return self._http.get(f"/v1/findings{qs}")

    def get(self, id: str) -> dict[str, Any]:
        res = self._http.get(f"/v1/findings/{id}")
        return res["finding"]

    def update(self, id: str, *, status: FindingStatus) -> dict[str, Any]:
        res = self._http.patch(f"/v1/findings/{id}", json={"status": status})
        return res["finding"]
