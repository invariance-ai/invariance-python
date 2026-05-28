from __future__ import annotations

from typing import Any

from ._types import Node, RunObservabilitySummary, StepKind, StepObservability


def summarize_run_observability(run_id: str, nodes: list[Node]) -> RunObservabilitySummary:
    steps = [_step_observability(node) for node in nodes]
    return {
        "run_id": run_id,
        "step_count": len(nodes),
        "llm_call_count": sum(1 for step in steps if step["kind"] == "llm"),
        "tool_call_count": sum(1 for step in steps if step["kind"] == "tool"),
        "error_count": sum(1 for step in steps if step["status"] == "error"),
        "total_input_tokens": sum(step["input_tokens"] for step in steps),
        "total_output_tokens": sum(step["output_tokens"] for step in steps),
        "total_cache_read_tokens": sum(step["cache_read_tokens"] for step in steps),
        "total_cache_write_tokens": sum(step["cache_write_tokens"] for step in steps),
        "total_words_created": sum(step["words_created"] for step in steps),
        "total_duration_ms": sum(step["duration_ms"] or 0 for step in steps),
        "steps": steps,
    }


def _step_observability(node: Node) -> StepObservability:
    metadata = _as_dict(node.get("metadata"))
    llm = _as_dict(metadata.get("llm"))
    output = _as_dict(node.get("output"))
    return {
        "node_id": node["id"],
        "action_type": node["action_type"],
        "type": node.get("type"),
        "kind": _kind_for_node(node),
        "status": "ok" if node.get("error") is None else "error",
        "input_tokens": _as_int(llm.get("input_tokens")),
        "output_tokens": _as_int(llm.get("output_tokens")),
        "cache_read_tokens": _as_int(llm.get("cache_read_tokens")),
        "cache_write_tokens": _as_int(llm.get("cache_write_tokens")),
        "words_created": (
            _as_int(metadata.get("words_created"))
            or _as_int(output.get("words_created"))
            or _count_words(output.get("text") if isinstance(output.get("text"), str) else None)
        ),
        "duration_ms": node.get("duration_ms"),
    }


def _kind_for_node(node: Node) -> StepKind:
    metadata = _as_dict(node.get("metadata"))
    action_type = node.get("action_type", "")
    node_type = node.get("type")
    if node_type == "llm_call" or action_type.startswith("llm."):
        return "llm"
    if node_type == "tool_call" or metadata.get("tool_name") is not None:
        return "tool"
    if node_type == "message" or "message" in action_type or "prompt" in action_type:
        return "message"
    return "step"


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_int(value: Any) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _count_words(text: str | None) -> int:
    return len([part for part in (text or "").strip().split() if part])
