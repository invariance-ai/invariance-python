"""Company DNA — edge-candidate promotion lifecycle.

DNA edge candidates are relationships discovered between objects. They start as
``proposed`` and move through ``accepted``/``rejected`` to ``promoted``.
Promoting an accepted ``semantic_similarity`` candidate writes a durable
semantic link that preserves its evidence and provenance::

    cands = inv.dna.list_edge_candidates(status="proposed")
    inv.dna.accept_edge_candidate(cands["data"][0]["id"])
    inv.dna.promote_edge_candidate(cands["data"][0]["id"])  # -> semantic link
"""

from __future__ import annotations

from typing import Any, Literal

from ._query import with_query
from .client import HttpClient

DnaEdgeCandidateStatus = Literal[
    "proposed", "accepted", "rejected", "expired", "promoted"
]


class DnaResource:
    def __init__(self, http: HttpClient) -> None:
        self._http = http

    def list_edge_candidates(
        self,
        *,
        project_id: str | None = None,
        object_id: str | None = None,
        relation_kind: str | None = None,
        status: DnaEdgeCandidateStatus | None = None,
        cursor: str | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        """List discovered edge candidates. Output: {data: [...], next_cursor}."""
        return self._http.get(
            with_query(
                "/v1/dna/edge-candidates",
                project_id=project_id,
                object_id=object_id,
                relation_kind=relation_kind,
                status=status,
                cursor=cursor,
                limit=limit,
            )
        )

    def list_objects(
        self,
        *,
        project_id: str | None = None,
        kind: str | None = None,
        q: str | None = None,
        cursor: str | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        """List DNA objects. Output: {data: [...], next_cursor}."""
        return self._http.get(
            with_query(
                "/v1/dna/objects",
                project_id=project_id,
                kind=kind,
                q=q,
                cursor=cursor,
                limit=limit,
            )
        )

    def list_object_mentions(
        self,
        *,
        project_id: str | None = None,
        event_id: str | None = None,
        chunk_id: str | None = None,
        object_id: str | None = None,
        mention_type: str | None = None,
        cursor: str | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        """List extracted object mentions. Output: {data: [...], next_cursor}."""
        return self._http.get(
            with_query(
                "/v1/dna/object-mentions",
                project_id=project_id,
                event_id=event_id,
                chunk_id=chunk_id,
                object_id=object_id,
                mention_type=mention_type,
                cursor=cursor,
                limit=limit,
            )
        )

    def list_edges(
        self,
        *,
        run_id: str | None = None,
        kind: str | None = None,
        entity_id: str | None = None,
        cursor: str | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        """List durable DNA edges (e.g. a run's operational graph).

        Output: {data: [...], next_cursor}.
        """
        return self._http.get(
            with_query(
                "/v1/dna/edges",
                run_id=run_id,
                kind=kind,
                entity_id=entity_id,
                cursor=cursor,
                limit=limit,
            )
        )

    def accept_edge_candidate(
        self, id: str, *, project_id: str | None = None
    ) -> dict[str, Any]:
        """Accept a proposed candidate, making it eligible for promotion."""
        body: dict[str, Any] = {}
        if project_id is not None:
            body["project_id"] = project_id
        res = self._http.post(f"/v1/dna/edge-candidates/{id}/accept", json=body)
        return res["candidate"]

    def reject_edge_candidate(
        self, id: str, *, project_id: str | None = None
    ) -> dict[str, Any]:
        """Reject a candidate so it is never promoted."""
        body: dict[str, Any] = {}
        if project_id is not None:
            body["project_id"] = project_id
        res = self._http.post(f"/v1/dna/edge-candidates/{id}/reject", json=body)
        return res["candidate"]

    def promote_edge_candidate(
        self,
        id: str,
        *,
        dry_run: bool = False,
        project_id: str | None = None,
    ) -> dict[str, Any]:
        """Promote an accepted candidate into a durable semantic link.

        The candidate must be ``accepted``, carry a ``semantic_similarity``
        signal, and have at least two evidence chunks, or the API returns 422.
        Idempotent: re-promoting returns the existing link with
        ``already_promoted=True``. With ``dry_run=True`` the would-be link is
        returned but nothing is written.

        Output: ``{semantic_link, candidate, already_promoted, dry_run}``.
        """
        body: dict[str, Any] = {"dry_run": dry_run}
        if project_id is not None:
            body["project_id"] = project_id
        return self._http.post(f"/v1/dna/edge-candidates/{id}/promote", json=body)
