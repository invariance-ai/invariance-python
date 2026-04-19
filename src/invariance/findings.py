"""Findings — high-level incidents created by monitors."""

from __future__ import annotations

from urllib.parse import urlencode

from ._types import Finding, FindingList, FindingStatus
from .client import HttpClient


class FindingsResource:
    def __init__(self, http: HttpClient) -> None:
        self._http = http

    def list(
        self,
        *,
        cursor: str | None = None,
        limit: int | None = None,
    ) -> FindingList:
        params: dict[str, str] = {}
        if cursor:
            params["cursor"] = cursor
        if limit:
            params["limit"] = str(limit)
        qs = f"?{urlencode(params)}" if params else ""
        return self._http.get(f"/v1/findings{qs}")

    def get(self, id: str) -> Finding:
        res = self._http.get(f"/v1/findings/{id}")
        return res["finding"]

    def update(self, id: str, *, status: FindingStatus) -> Finding:
        res = self._http.patch(f"/v1/findings/{id}", json={"status": status})
        return res["finding"]
