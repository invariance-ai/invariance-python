"""Divergences — detected gaps between expected and observed agent behaviour.

Read the queue (``list``/``get``) and triage it (``update`` the status to
``accepted``/``dismissed``/``converted_to_monitor``). Reads accept an agent
**or** operator key.
"""

from __future__ import annotations

from ._query import with_query
from ._types import Divergence, DivergenceKind, DivergenceList, DivergenceStatus, Severity
from .client import HttpClient


class DivergencesResource:
    def __init__(self, http: HttpClient) -> None:
        self._http = http

    def list(
        self,
        *,
        run_id: str | None = None,
        kind: DivergenceKind | None = None,
        severity: Severity | None = None,
        status: DivergenceStatus | None = None,
        cursor: str | None = None,
        limit: int | None = None,
    ) -> DivergenceList:
        return self._http.get(
            with_query(
                "/v1/divergences",
                run_id=run_id,
                kind=kind,
                severity=severity,
                status=status,
                cursor=cursor,
                limit=limit,
            )
        )

    def get(self, id: str) -> Divergence:
        res = self._http.get(f"/v1/divergences/{id}")
        return res["divergence"]

    def update(self, id: str, *, status: DivergenceStatus) -> Divergence:
        res = self._http.patch(f"/v1/divergences/{id}", json={"status": status})
        return res["divergence"]
