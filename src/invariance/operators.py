"""Operators — unified concept covering autonomous agents and human teammates.

Wire shape mirrors :class:`AgentsResource` intentionally; the server enforces
uniqueness differently per ``operator_type``.
"""

from __future__ import annotations

from ._query import with_query
from ._types import (
    CreateOperatorResponse,
    Operator,
    OperatorList,
    OperatorMeResponse,
    OperatorType,
)
from .client import HttpClient


class OperatorsResource:
    def __init__(self, http: HttpClient) -> None:
        self._http = http

    def me(self) -> OperatorMeResponse:
        return self._http.get("/v1/operators/me")

    def create(
        self,
        *,
        name: str,
        project_id: str,
        operator_type: OperatorType | None = None,
        public_key: str | None = None,
        key_mode: str | None = None,
    ) -> CreateOperatorResponse:
        body: dict[str, object] = {"name": name, "project_id": project_id}
        if operator_type is not None:
            body["operator_type"] = operator_type
        if public_key is not None:
            body["public_key"] = public_key
        if key_mode is not None:
            body["key_mode"] = key_mode
        return self._http.post("/v1/operators", json=body)

    def list(
        self,
        *,
        project_id: str,
        operator_type: OperatorType | None = None,
    ) -> OperatorList:
        return self._http.get(
            with_query(
                "/v1/operators",
                project_id=project_id,
                operator_type=operator_type,
            )
        )

    def get(self, id: str) -> Operator:
        res = self._http.get(f"/v1/operators/{id}")
        return res["operator"]
