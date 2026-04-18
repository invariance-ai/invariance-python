"""Reviews — human / agent adjudication on findings.

A Review attaches to a Finding (1:1) when the monitor sets
``creates_review=True``. Lifecycle: ``pending → claimed → passed |
failed | needs_fix``.
"""

from __future__ import annotations

from typing import Any, Literal
from urllib.parse import urlencode

from .client import HttpClient


ReviewDecision = Literal["passed", "failed", "needs_fix"]


class ReviewsResource:
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
        return self._http.get(f"/v1/reviews{qs}")

    def get(self, id: str) -> dict[str, Any]:
        res = self._http.get(f"/v1/reviews/{id}")
        return res["review"]

    def claim(self, id: str, *, notes: str | None = None) -> dict[str, Any]:
        body: dict[str, Any] = {"status": "claimed"}
        if notes is not None:
            body["notes"] = notes
        res = self._http.patch(f"/v1/reviews/{id}", json=body)
        return res["review"]

    def unclaim(self, id: str, *, notes: str | None = None) -> dict[str, Any]:
        body: dict[str, Any] = {"status": "pending"}
        if notes is not None:
            body["notes"] = notes
        res = self._http.patch(f"/v1/reviews/{id}", json=body)
        return res["review"]

    def resolve(
        self,
        id: str,
        *,
        decision: ReviewDecision,
        notes: str | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"decision": decision}
        if notes is not None:
            body["notes"] = notes
        return self._http.patch(f"/v1/reviews/{id}", json=body)
