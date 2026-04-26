"""Declarative custom node types for typed nodes.

Declare a node type once, stamp it on writes, and reference it from
Monitor selectors (``on.node(type=...)``). The schema is informational
only — no runtime validation — but IDE/type-checkers narrow
``custom_fields`` to the declared generic when callers pass a
``TypedDict``.

>>> class BillingFields(TypedDict):
...     user_id: str
...     amount_cents: int
>>> BillingCharge = define_node_type("billing_charge", BillingFields)
>>> with run.step("tool.use", type=BillingCharge.type,
...               custom_fields={"user_id": "u_1", "amount_cents": 500}) as s:
...     ...
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Generic, TypeVar

from .client import HttpClient

T = TypeVar("T", bound=dict)


@dataclass(frozen=True)
class NodeType(Generic[T]):
    """A declared custom node type with a typed ``custom_fields`` shape."""

    type: str

    def node(
        self,
        action_type: str,
        *,
        input: Any | None = None,
        output: Any | None = None,
        error: Any | None = None,
        metadata: dict[str, Any] | None = None,
        custom_fields: T | None = None,
        parent_id: str | None = None,
    ) -> dict[str, Any]:
        """Build a node-write dict stamped with this type.

        Pass the result to ``client.nodes.write(run_id, [node_dict])``.
        """
        body: dict[str, Any] = {"action_type": action_type, "type": self.type}
        if input is not None:
            body["input"] = input
        if output is not None:
            body["output"] = output
        if error is not None:
            body["error"] = error
        if metadata is not None:
            body["metadata"] = metadata
        if custom_fields is not None:
            body["custom_fields"] = custom_fields
        if parent_id is not None:
            body["parent_id"] = parent_id
        return body


def define_node_type(type: str, _schema: type | None = None) -> NodeType:
    """Convenience factory mirroring the TS ``defineNodeType`` surface.

    The optional second argument is a ``TypedDict`` class used only by
    type-checkers to infer the ``custom_fields`` generic — it's ignored
    at runtime.
    """
    return NodeType(type)


# ── Registry API ────────────────────────────────────────────────────────────


def _build_register_body(
    name: str,
    *,
    display_name: str | None = None,
    custom_fields_schema: dict[str, Any] | None = None,
    aggregation_hints: dict[str, Any] | None = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {"name": name}
    if display_name is not None:
        body["display_name"] = display_name
    if custom_fields_schema is not None:
        body["custom_fields_schema"] = custom_fields_schema
    if aggregation_hints is not None:
        body["aggregation_hints"] = aggregation_hints
    return body


class NodeTypesResource:
    """Project-scoped registry of custom node types.

    Mirrors the TS ``inv.nodeTypes`` resource — declarative type names,
    optional ``custom_fields`` schema, and aggregation hints used by
    Monitors. Schema is informational; the platform does not enforce
    field types at write time.
    """

    def __init__(self, http: HttpClient) -> None:
        self._http = http

    def list(self) -> list[dict[str, Any]]:
        res = self._http.get("/v1/node-types")
        return res["data"]

    def register(
        self,
        name: str,
        *,
        display_name: str | None = None,
        custom_fields_schema: dict[str, Any] | None = None,
        aggregation_hints: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        body = _build_register_body(
            name,
            display_name=display_name,
            custom_fields_schema=custom_fields_schema,
            aggregation_hints=aggregation_hints,
        )
        res = self._http.post("/v1/node-types", json=body)
        return res["node_type"]
