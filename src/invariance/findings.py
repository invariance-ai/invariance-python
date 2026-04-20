"""Findings — high-level incidents created by monitors."""

from __future__ import annotations

from ._types import Finding, FindingList, FindingStatus
from .client import HttpClient
from ._query import with_query


class FindingsResource:
    def __init__(self, http: HttpClient) -> None:
        self._http = http

    def list(
        self,
        *,
        cursor: str | None = None,
        limit: int | None = None,
    ) -> FindingList:
        return self._http.get(with_query("/v1/findings", cursor=cursor, limit=limit))

    def get(self, id: str) -> Finding:
        res = self._http.get(f"/v1/findings/{id}")
        return res["finding"]

    def update(self, id: str, *, status: FindingStatus) -> Finding:
        res = self._http.patch(f"/v1/findings/{id}", json={"status": status})
        return res["finding"]
