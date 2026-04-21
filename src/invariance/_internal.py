from __future__ import annotations

import secrets
import time
from typing import Any

from .crypto import hash_node_payload, sign_ed25519


def random_node_id() -> str:
    return f"node_{secrets.token_hex(8)}"


def now_ms() -> int:
    return int(time.time() * 1000)


def build_node_body(
    *,
    run_id: str,
    agent_id: str,
    last_hash: str | None,
    signing_key: str | None,
    id: str,
    action_type: str,
    type: str | None = None,
    input: Any | None = None,
    output: Any | None,
    error: Any | None,
    metadata: dict[str, Any] | None,
    custom_fields: dict[str, Any] | None,
    parent_id: str | None,
    timestamp: int | None,
    duration_ms: int | None,
    handoff_from: str | None = None,
    handoff_to: str | None = None,
    handoff_reason: str | None = None,
) -> tuple[dict[str, Any], str | None]:
    """Build a node POST body. Returns (body, new_last_hash).

    When ``signing_key`` is set, the node is signed and a new tail hash is
    returned so the caller can chain the next signed node. Otherwise the
    passed-in ``last_hash`` is returned unchanged.
    """
    body: dict[str, Any] = {
        "run_id": run_id,
        "id": id,
        "action_type": action_type,
    }
    if type is not None:
        body["type"] = type
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
    if duration_ms is not None:
        body["duration_ms"] = duration_ms
    if handoff_from is not None:
        body["handoff_from"] = handoff_from
    if handoff_to is not None:
        body["handoff_to"] = handoff_to
    if handoff_reason is not None:
        body["handoff_reason"] = handoff_reason

    new_last_hash = last_hash
    if signing_key:
        ts = timestamp if timestamp is not None else now_ms()
        prev = [] if last_hash is None else [last_hash]
        payload: dict[str, Any] = {
            "id": id,
            "run_id": run_id,
            "agent_id": agent_id,
            "parent_id": parent_id,
            "action_type": action_type,
            "input": input,
            "output": output,
            "error": error,
            "metadata": metadata if metadata is not None else {},
            "custom_fields": custom_fields if custom_fields is not None else {},
            "timestamp": ts,
            "duration_ms": duration_ms,
            "previous_hashes": prev,
        }
        if handoff_from is not None:
            payload["handoff_from"] = handoff_from
        if handoff_to is not None:
            payload["handoff_to"] = handoff_to
        if handoff_reason is not None:
            payload["handoff_reason"] = handoff_reason
        body["timestamp"] = ts
        body["previous_hashes"] = prev
        digest = hash_node_payload(payload)
        body["signature"] = sign_ed25519(digest, signing_key)
        new_last_hash = digest
    elif timestamp is not None:
        body["timestamp"] = timestamp
    return body, new_last_hash
