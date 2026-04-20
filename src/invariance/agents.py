from __future__ import annotations

from ._types import Agent, AgentList, CreateAgentResponse, GetMeResponse
from .client import HttpClient
from ._query import with_query


class AgentsResource:
    def __init__(self, http: HttpClient) -> None:
        self._http = http

    def me(self) -> GetMeResponse:
        return self._http.get("/v1/agents/me")

    def set_public_key(self, public_key: str) -> Agent:
        """Register or rotate the caller's Ed25519 public key (64-char hex)."""
        res = self._http.request("PUT", "/v1/agents/me/key", json={"public_key": public_key})
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
