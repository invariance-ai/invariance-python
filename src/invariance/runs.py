from __future__ import annotations

import secrets
import time
from typing import Any
from urllib.parse import urlencode

from .client import HttpClient
from .crypto import hash_node_payload, sign_ed25519


def _random_node_id() -> str:
    return f"node_{secrets.token_hex(8)}"


class Run:
    """Wraps a backend session as a developer-facing Run.

    When constructed with a signing_key (Ed25519 private-key hex), every
    node written through this run is signed client-side. The Run tracks
    its tail hash so `previous_hashes` defaults correctly.
    """

    def __init__(
        self,
        http: HttpClient,
        session: dict[str, Any],
        signing_key: str | None = None,
    ) -> None:
        self._http = http
        self._session = session
        self._signing_key = signing_key
        self._last_hash: str | None = None

    @property
    def session_id(self) -> str:
        return self._session["id"]

    @property
    def name(self) -> str:
        return self._session["name"]

    @property
    def status(self) -> str:
        return self._session["status"]

    def node(
        self,
        *,
        action_type: str,
        input: Any | None = None,
        output: Any | None = None,
        error: Any | None = None,
        metadata: dict[str, Any] | None = None,
        custom_fields: dict[str, Any] | None = None,
        timestamp: int | None = None,
        duration_ms: int | None = None,
        parent_id: str | None = None,
        previous_hashes: list[str] | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "session_id": self.session_id,
            "action_type": action_type,
        }
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
        if duration_ms is not None:
            body["duration_ms"] = duration_ms
        if parent_id is not None:
            body["parent_id"] = parent_id

        if self._signing_key:
            node_id = _random_node_id()
            ts = timestamp if timestamp is not None else int(time.time() * 1000)
            prev = previous_hashes if previous_hashes is not None else (
                [] if self._last_hash is None else [self._last_hash]
            )
            payload = {
                "id": node_id,
                "session_id": self.session_id,
                "agent_id": self._session["agent_id"],
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
            h = hash_node_payload(payload)
            body["id"] = node_id
            body["timestamp"] = ts
            body["previous_hashes"] = prev
            body["signature"] = sign_ed25519(h, self._signing_key)
        else:
            if timestamp is not None:
                body["timestamp"] = timestamp
            if previous_hashes is not None:
                body["previous_hashes"] = previous_hashes

        res = self._http.post("/v1/nodes", json=body)
        node = res["data"][0]
        if "hash" in node:
            self._last_hash = node["hash"]
        return node

    def verify(self) -> dict[str, Any]:
        return self._http.get(f"/v1/sessions/{self.session_id}/verify")

    def finish(self) -> dict[str, Any]:
        res = self._http.patch(
            f"/v1/sessions/{self.session_id}",
            json={"status": "completed"},
        )
        return res["session"]

    def fail(self, error: str | None = None) -> dict[str, Any]:
        body: dict[str, Any] = {"status": "failed"}
        if error:
            body["metadata"] = {"error": error}
        res = self._http.patch(f"/v1/sessions/{self.session_id}", json=body)
        return res["session"]


class RunsResource:
    def __init__(self, http: HttpClient, signing_key: str | None = None) -> None:
        self._http = http
        self._signing_key = signing_key

    def start(
        self,
        name: str | None = None,
        metadata: dict[str, Any] | None = None,
        *,
        signing_key: str | None = None,
    ) -> Run:
        body: dict[str, Any] = {}
        if name is not None:
            body["name"] = name
        if metadata is not None:
            body["metadata"] = metadata
        res = self._http.post("/v1/sessions", json=body)
        return Run(self._http, res["session"], signing_key or self._signing_key)

    def list(
        self,
        *,
        cursor: str | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        params: dict[str, str] = {}
        if cursor:
            params["cursor"] = cursor
        if limit:
            params["limit"] = str(limit)
        qs = f"?{urlencode(params)}" if params else ""
        return self._http.get(f"/v1/sessions{qs}")

    def get(self, id: str) -> Run:
        res = self._http.get(f"/v1/sessions/{id}")
        return Run(self._http, res["session"], self._signing_key)
