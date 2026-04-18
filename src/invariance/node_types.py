"""Declarative custom node types for typed trace nodes.

Declare a node type once, stamp it on writes, and reference it from
Monitor selectors (``on.node(type=...)``). The schema is informational
only — no runtime validation — but IDE/type-checker users get hints
when they pass a ``TypedDict`` as ``schema``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class NodeType:
    """A declared custom node type.

    >>> BillingCharge = NodeType("billing_charge")
    >>> run.step("tool.use", type=BillingCharge.type, custom_fields={...})
    """

    type: str

    def node(
        self,
        action_type: str,
        *,
        input: Any | None = None,
        output: Any | None = None,
        error: Any | None = None,
        metadata: dict[str, Any] | None = None,
        custom_fields: dict[str, Any] | None = None,
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


def define_node_type(type: str) -> NodeType:
    """Convenience factory mirroring the TS ``defineNodeType`` surface."""
    return NodeType(type)
