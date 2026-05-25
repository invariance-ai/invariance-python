"""Saved views — persisted dashboard queries over the data plane.

Full CRUD plus an ad-hoc ``run``. A query targets one ``QuerySource``
(executions/events/runs/nodes/captures) and is shaped by a ``QuerySpec``
(fields/filters/group_by/aggregation/...). ``run`` executes EITHER a stored
view (``saved_view_id``) OR an inline ``source``+``spec`` — exactly one, never
both. Reads accept an agent **or** operator key.
"""

from __future__ import annotations

from typing import Any

from ._types import (
    DashboardViz,
    QueryResult,
    QuerySource,
    QuerySpec,
    SavedView,
    SavedViewList,
    SavedViewVisibility,
)
from .client import HttpClient


class SavedViewsResource:
    def __init__(self, http: HttpClient) -> None:
        self._http = http

    def list(self) -> SavedViewList:
        """List saved views. NOTE: this envelope has no ``next_cursor``."""
        return self._http.get("/v1/saved-views")

    def create(
        self,
        *,
        name: str,
        source: QuerySource,
        spec: QuerySpec,
        viz: DashboardViz | None = None,
        visibility: SavedViewVisibility | None = None,
    ) -> SavedView:
        body: dict[str, Any] = {"name": name, "source": source, "spec": spec}
        if viz is not None:
            body["viz"] = viz
        if visibility is not None:
            body["visibility"] = visibility
        res = self._http.post("/v1/saved-views", json=body)
        return res["view"]

    def get(self, id: str) -> SavedView:
        res = self._http.get(f"/v1/saved-views/{id}")
        return res["view"]

    def update(
        self,
        id: str,
        *,
        name: str | None = None,
        source: QuerySource | None = None,
        spec: QuerySpec | None = None,
        viz: DashboardViz | None = None,
        visibility: SavedViewVisibility | None = None,
    ) -> SavedView:
        body: dict[str, Any] = {}
        if name is not None:
            body["name"] = name
        if source is not None:
            body["source"] = source
        if spec is not None:
            body["spec"] = spec
        if viz is not None:
            body["viz"] = viz
        if visibility is not None:
            body["visibility"] = visibility
        res = self._http.patch(f"/v1/saved-views/{id}", json=body)
        return res["view"]

    def delete(self, id: str) -> None:
        self._http.delete(f"/v1/saved-views/{id}")

    def run(
        self,
        *,
        saved_view_id: str | None = None,
        source: QuerySource | None = None,
        spec: QuerySpec | None = None,
    ) -> QueryResult:
        """Execute a saved view by id, or an ad-hoc ``source``+``spec`` query.

        Provide EXACTLY ONE of ``saved_view_id`` or ``source`` — passing both
        (or neither) raises :class:`ValueError` before any request is made.
        """
        if saved_view_id is not None and source is not None:
            raise ValueError(
                "run() takes exactly one of saved_view_id or source, not both"
            )
        if saved_view_id is None and source is None:
            raise ValueError("run() requires either saved_view_id or source")
        if saved_view_id is not None:
            body: dict[str, Any] = {"saved_view_id": saved_view_id}
        else:
            body = {"source": source}
            if spec is not None:
                body["spec"] = spec
        res = self._http.post("/v1/saved-views/run", json=body)
        return res["result"]
