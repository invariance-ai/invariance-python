"""Recipes — read-only registry of built-in operational checks."""

from __future__ import annotations

from ._query import with_query
from ._types import GuardrailMode, Recipe, RecipeList
from .client import HttpClient


class RecipesResource:
    def __init__(self, http: HttpClient) -> None:
        self._http = http

    def list(
        self,
        *,
        cursor: str | None = None,
        limit: int | None = None,
    ) -> RecipeList:
        return self._http.get(with_query("/v1/recipes", cursor=cursor, limit=limit))

    def get(self, id_or_slug: str) -> Recipe:
        res = self._http.get(f"/v1/recipes/{id_or_slug}")
        return res["recipe"]

    def update(
        self,
        id: str,
        *,
        enabled: bool | None = None,
        default_mode: GuardrailMode | None = None,
    ) -> Recipe:
        body: dict[str, object] = {}
        if enabled is not None:
            body["enabled"] = enabled
        if default_mode is not None:
            body["default_mode"] = default_mode
        res = self._http.patch(f"/v1/recipes/{id}", json=body)
        return res["recipe"]
