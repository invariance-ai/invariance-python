from __future__ import annotations

from typing import Any

from .client import HttpClient


class AgentsResource:
    def __init__(self, http: HttpClient) -> None:
        self._http = http

    def me(self) -> dict[str, Any]:
        return self._http.get("/v1/agents/me")

    def set_public_key(self, public_key: str) -> dict[str, Any]:
        """Register or rotate the caller's Ed25519 public key (64-char hex)."""
        res = self._http.request("PUT", "/v1/agents/me/key", json={"public_key": public_key})
        return res["agent"]
