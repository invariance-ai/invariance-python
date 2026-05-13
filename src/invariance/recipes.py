"""Read-only registry of built-in operational checks.

Use ``client.guardrails.create(recipe_id=...)`` to promote a recipe into a
per-agent guardrail.
"""

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
        patch: dict[str, object] = {}
        if enabled is not None:
            patch["enabled"] = enabled
        if default_mode is not None:
            patch["default_mode"] = default_mode
        res = self._http.request("PATCH", f"/v1/recipes/{id}", json=patch)
        return res["recipe"]
