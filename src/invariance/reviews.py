"""Reviews — human / agent adjudication on findings.

A Review attaches to a Finding (1:1) when the monitor sets
``creates_review=True``. Lifecycle: ``pending → claimed → passed |
failed | needs_fix``.
"""

from __future__ import annotations

from ._types import Review, ReviewDecision, ReviewList, ReviewResponse
from .client import HttpClient
from ._query import with_query


class ReviewsResource:
    def __init__(self, http: HttpClient) -> None:
        self._http = http

    def list(
        self,
        *,
        cursor: str | None = None,
        limit: int | None = None,
    ) -> ReviewList:
        return self._http.get(with_query("/v1/reviews", cursor=cursor, limit=limit))

    def get(self, id: str) -> Review:
        res = self._http.get(f"/v1/reviews/{id}")
        return res["review"]

    def claim(self, id: str, *, notes: str | None = None) -> Review:
        body: dict[str, object] = {"status": "claimed"}
        if notes is not None:
            body["notes"] = notes
        res = self._http.patch(f"/v1/reviews/{id}", json=body)
        return res["review"]

    def unclaim(self, id: str, *, notes: str | None = None) -> Review:
        body: dict[str, object] = {"status": "pending"}
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
    ) -> ReviewResponse:
        """Resolve a review. Returns ``{review, finding}``."""
        body: dict[str, object] = {"decision": decision}
        if notes is not None:
            body["notes"] = notes
        return self._http.patch(f"/v1/reviews/{id}", json=body)
