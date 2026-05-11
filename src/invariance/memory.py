"""Memory primitives — record what agents read/write about subjects.

Mirrors the TS SDK ``MemoryResource`` (``/v1/memory/read``, ``/v1/memory/write``).
"""

from __future__ import annotations

import os
from typing import Any

from ._types import (
    EvidenceRef,
    MemoryReadResponse,
    MemorySource,
    MemorySubjectType,
    MemoryWriteResponse,
)
from .client import HttpClient


def _env_ids() -> tuple[str | None, str | None]:
    return os.environ.get("INVARIANCE_RUN_ID"), os.environ.get("INVARIANCE_NODE_ID")


def _build_read_body(
    *,
    subject_type: MemorySubjectType,
    subject_id: str,
    key: str,
    used_for: str,
    run_id: str | None,
    node_id: str | None,
) -> dict[str, Any]:
    env_run, env_node = _env_ids()
    body: dict[str, Any] = {
        "subject_type": subject_type,
        "subject_id": subject_id,
        "key": key,
        "used_for": used_for,
    }
    final_run = run_id if run_id is not None else env_run
    final_node = node_id if node_id is not None else env_node
    if final_run is not None:
        body["run_id"] = final_run
    if final_node is not None:
        body["node_id"] = final_node
    return body


def _build_write_body(
    *,
    subject_type: MemorySubjectType,
    subject_id: str,
    key: str,
    value: Any,
    used_for: str,
    run_id: str | None,
    node_id: str | None,
    source: MemorySource | None,
    confidence: float | None,
    provenance: list[EvidenceRef] | None,
    valid_until: str | None,
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
