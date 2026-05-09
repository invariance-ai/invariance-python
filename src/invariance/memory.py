"""Memory — record agent reads/writes against subject beliefs.

Mirrors the TypeScript SDK's ``inv.memory`` resource. POST to
``/v1/memory/read`` and ``/v1/memory/write``; both return
``{access, record}``.
"""

from __future__ import annotations

import os
from typing import Any, Literal, TypedDict

from .client import HttpClient


# ── Subject + source enums ─────────────────────────────────────────────────


MemorySubjectType = Literal[
    "customer",
    "account",
    "user",
    "policy",
    "workflow",
    "preference",
]

MemorySource = Literal[
    "agent_write",
    "human_write",
    "crm",
    "ticket",
    "policy_doc",
    "external_system",
]

MemoryAccessType = Literal["read", "write"]

MemoryDivergenceKind = Literal[
    "stale_memory",
    "contradicted_memory",
    "unsupported_memory",
    "overgeneralized_memory",
    "memory_used_without_source",
    "memory_caused_bad_action",
    "memory_not_updated_after_ground_truth_change",
]

MemoryDivergenceStatus = Literal["open", "dismissed", "resolved"]


# ── Records ────────────────────────────────────────────────────────────────


class EvidenceRef(TypedDict, total=False):
    kind: Literal["node", "tool_call", "llm_call", "document", "system_record"]
    id: str
    uri: str
    excerpt: str


class SystemRecord(TypedDict):
    source: MemorySource
    external_id: str
    fetched_at: str
    fields: dict[str, Any]


class MemoryRecord(TypedDict):
    id: str
    agent_id: str
    subject_type: MemorySubjectType
    subject_id: str
    claim: str
    value: Any
    source: MemorySource
    confidence: float
    valid_from: str
    valid_until: str | None
    last_verified_at: str | None
    superseded_by: str | None
    provenance: list[EvidenceRef]


class MemoryAccess(TypedDict):
    id: str
    run_id: str
    node_id: str
    agent_id: str
    access_type: MemoryAccessType
    subject_type: MemorySubjectType
    subject_id: str
    key: str
    value: Any
    used_for: str
    source_node_id: str | None
    timestamp: str


class MemoryReadResponse(TypedDict):
    access: MemoryAccess
    record: MemoryRecord | None


class MemoryWriteResponse(TypedDict):
    access: MemoryAccess
    record: MemoryRecord


# ── Body builders ──────────────────────────────────────────────────────────


def _env_ids() -> dict[str, str]:
    out: dict[str, str] = {}
    run_id = os.environ.get("INVARIANCE_RUN_ID")
    node_id = os.environ.get("INVARIANCE_NODE_ID")
    if run_id is not None:
        out["run_id"] = run_id
    if node_id is not None:
        out["node_id"] = node_id
    return out


def _build_read_body(
    *,
    subject_type: MemorySubjectType,
    subject_id: str,
    key: str,
    used_for: str,
    run_id: str | None = None,
    node_id: str | None = None,
) -> dict[str, Any]:
    env = _env_ids()
    body: dict[str, Any] = {
        "subject_type": subject_type,
        "subject_id": subject_id,
        "key": key,
        "used_for": used_for,
    }
    rid = run_id if run_id is not None else env.get("run_id")
    nid = node_id if node_id is not None else env.get("node_id")
    if rid is not None:
        body["run_id"] = rid
    if nid is not None:
        body["node_id"] = nid
    return body


def _build_write_body(
    *,
    subject_type: MemorySubjectType,
    subject_id: str,
    key: str,
    value: Any,
    used_for: str,
    run_id: str | None = None,
    node_id: str | None = None,
    source: MemorySource | None = None,
    confidence: float | None = None,
    provenance: list[EvidenceRef] | None = None,
    valid_until: str | None = None,
) -> dict[str, Any]:
    body = _build_read_body(
        subject_type=subject_type,
        subject_id=subject_id,
        key=key,
        used_for=used_for,
        run_id=run_id,
        node_id=node_id,
    )
    body["value"] = value
    body["source"] = source if source is not None else "agent_write"
    body["confidence"] = confidence if confidence is not None else 1.0
    if provenance is not None:
        body["provenance"] = provenance
    if valid_until is not None:
        body["valid_until"] = valid_until
    return body


# ── Resource ───────────────────────────────────────────────────────────────


class MemoryResource:
    def __init__(self, http: HttpClient) -> None:
        self._http = http

    def read(
        self,
        *,
        subject_type: MemorySubjectType,
        subject_id: str,
        key: str,
        used_for: str,
        run_id: str | None = None,
        node_id: str | None = None,
    ) -> MemoryReadResponse:
        body = _build_read_body(
            subject_type=subject_type,
            subject_id=subject_id,
            key=key,
            used_for=used_for,
            run_id=run_id,
            node_id=node_id,
        )
        return self._http.post("/v1/memory/read", json=body)

    def write(
        self,
        *,
        subject_type: MemorySubjectType,
        subject_id: str,
        key: str,
        value: Any,
        used_for: str,
        run_id: str | None = None,
        node_id: str | None = None,
        source: MemorySource | None = None,
        confidence: float | None = None,
        provenance: list[EvidenceRef] | None = None,
        valid_until: str | None = None,
    ) -> MemoryWriteResponse:
        body = _build_write_body(
            subject_type=subject_type,
            subject_id=subject_id,
            key=key,
            value=value,
            used_for=used_for,
            run_id=run_id,
            node_id=node_id,
            source=source,
            confidence=confidence,
            provenance=provenance,
            valid_until=valid_until,
        )
        return self._http.post("/v1/memory/write", json=body)
