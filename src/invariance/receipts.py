"""External receipts — proof of side effects in third-party systems.

A receipt records that something happened in an external system (a Stripe
refund, a Zendesk ticket, a Slack message, ...) so it can be correlated to a
run/node in the evidence graph.

Auth: ``create`` / ``create_batch`` require an **agent API key**
(``requireApiKey`` → 403 on operator tokens). ``list`` / ``get`` accept an
agent **or** operator key.
"""

from __future__ import annotations

from typing import Any

from ._query import with_query
from ._types import ExternalReceipt, ExternalReceiptList, ExternalReceiptSource
from .client import HttpClient


def _build_receipt_body(
    *,
    source: ExternalReceiptSource,
    kind: str,
    run_id: str | None = None,
    node_id: str | None = None,
    external_id: str | None = None,
    occurred_at: str | None = None,
    business_object_type: str | None = None,
    business_object_id: str | None = None,
    subject_type: str | None = None,
    subject_id: str | None = None,
    correlation_keys: dict[str, str] | None = None,
    payload: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {"source": source, "kind": kind}
    if run_id is not None:
        body["run_id"] = run_id
    if node_id is not None:
        body["node_id"] = node_id
    if external_id is not None:
        body["external_id"] = external_id
    if occurred_at is not None:
        body["occurred_at"] = occurred_at
    if business_object_type is not None:
        body["business_object_type"] = business_object_type
    if business_object_id is not None:
        body["business_object_id"] = business_object_id
    if subject_type is not None:
        body["subject_type"] = subject_type
    if subject_id is not None:
        body["subject_id"] = subject_id
    if correlation_keys is not None:
        body["correlation_keys"] = correlation_keys
    if payload is not None:
        body["payload"] = payload
    if metadata is not None:
        body["metadata"] = metadata
    return body


class ReceiptsResource:
    def __init__(self, http: HttpClient) -> None:
        self._http = http

    def create(
        self,
        *,
        source: ExternalReceiptSource,
        kind: str,
        run_id: str | None = None,
        node_id: str | None = None,
        external_id: str | None = None,
        occurred_at: str | None = None,
        business_object_type: str | None = None,
        business_object_id: str | None = None,
        subject_type: str | None = None,
        subject_id: str | None = None,
        correlation_keys: dict[str, str] | None = None,
        payload: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ExternalReceipt:
        """Record a single external receipt. Requires an agent API key."""
        body = _build_receipt_body(
            source=source,
            kind=kind,
            run_id=run_id,
            node_id=node_id,
            external_id=external_id,
            occurred_at=occurred_at,
            business_object_type=business_object_type,
            business_object_id=business_object_id,
            subject_type=subject_type,
            subject_id=subject_id,
            correlation_keys=correlation_keys,
            payload=payload,
            metadata=metadata,
        )
        res = self._http.post("/v1/receipts", json=body)
        return res["receipt"]

    def create_batch(
        self, receipts: list[dict[str, Any]]
    ) -> list[ExternalReceipt]:
        """Record many receipts in one call. Requires an agent API key.

        Each item is a ``CreateExternalReceiptRequest`` dict (``source`` and
        ``kind`` required).
        """
        res = self._http.post("/v1/receipts/batch", json={"receipts": receipts})
        return res["receipts"]

    def list(
        self,
        *,
        run_id: str | None = None,
        node_id: str | None = None,
        source: ExternalReceiptSource | None = None,
        kind: str | None = None,
        external_id: str | None = None,
        business_object_type: str | None = None,
        business_object_id: str | None = None,
        cursor: str | None = None,
        limit: int | None = None,
    ) -> ExternalReceiptList:
        return self._http.get(
            with_query(
                "/v1/receipts",
                run_id=run_id,
                node_id=node_id,
                source=source,
                kind=kind,
                external_id=external_id,
                business_object_type=business_object_type,
                business_object_id=business_object_id,
                cursor=cursor,
                limit=limit,
            )
        )

    def get(self, id: str) -> ExternalReceipt:
        res = self._http.get(f"/v1/receipts/{id}")
        return res["receipt"]
