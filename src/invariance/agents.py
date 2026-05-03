from __future__ import annotations

import time
from typing import Any

from ._types import Agent, AgentList, CreateAgentResponse, GetMeResponse
from .client import HttpClient
from ._query import with_query
from .crypto import get_public_key, hash_key_rotation_payload, sign_ed25519


class AgentsResource:
    def __init__(self, http: HttpClient) -> None:
        self._http = http

    def me(self) -> GetMeResponse:
        return self._http.get("/v1/agents/me")

    def set_public_key(self, public_key: str) -> Agent:
        """Register the caller's Ed25519 public key (bootstrap, 64-char hex).

        Prefer ``rotate_key`` when the agent already has a registered key —
        the backend rejects unsigned rotations.
        """
        res = self._http.request("PUT", "/v1/agents/me/key", json={"public_key": public_key})
        return res["agent"]

    def rotate_key(self, new_private_key: str, prev_public_key: str | None = None) -> Agent:
        """Rotate (or first-time register) this agent's Ed25519 public key with
        a signed payload proving control of the **new** private key. Required
        for rotation; recommended on bootstrap.
        """
        new_public_key = get_public_key(new_private_key)
        me = self.me()
        timestamp = int(time.time() * 1000)
        payload: dict[str, Any] = {
            "agent_id": me["agent"]["id"],
            "new_public_key": new_public_key,
            "prev_public_key": prev_public_key,
            "timestamp": timestamp,
        }
        digest = hash_key_rotation_payload(payload)
        signature = sign_ed25519(digest, new_private_key)
        res = self._http.request(
            "PUT",
            "/v1/agents/me/key",
            json={
                "public_key": new_public_key,
                "prev_public_key": prev_public_key,
                "timestamp": timestamp,
                "signature": signature,
            },
        )
        return res["agent"]

    def create(
        self,
        *,
        name: str,
        project_id: str,
        public_key: str | None = None,
        key_mode: str | None = None,
    ) -> CreateAgentResponse:
        """Create an agent in a caller-owned project (requires user JWT auth)."""
        body: dict[str, object] = {"name": name, "project_id": project_id}
        if public_key is not None:
            body["public_key"] = public_key
        if key_mode is not None:
            body["key_mode"] = key_mode
        return self._http.post("/v1/agents", json=body)

    def list(self, *, project_id: str) -> AgentList:
        return self._http.get(with_query("/v1/agents", project_id=project_id))

    def get(self, id: str) -> Agent:
        res = self._http.get(f"/v1/agents/{id}")
        return res["agent"]
