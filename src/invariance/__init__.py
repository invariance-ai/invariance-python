from __future__ import annotations

from .client import HttpClient, InvarianceApiError
from .runs import Run, RunsResource
from .nodes import NodesResource
from .agents import AgentsResource
from .crypto import (
    generate_keypair,
    get_public_key,
    sign_ed25519,
    verify_ed25519,
    hash_node_payload,
    stable_stringify,
    sha256_hex,
)

DEFAULT_API_URL = "https://api.invariance.dev"

__all__ = [
    "Invariance",
    "InvarianceApiError",
    "Run",
    "RunsResource",
    "NodesResource",
    "AgentsResource",
    "generate_keypair",
    "get_public_key",
    "sign_ed25519",
    "verify_ed25519",
    "hash_node_payload",
    "stable_stringify",
    "sha256_hex",
]


class Invariance:
    def __init__(
        self,
        api_key: str,
        api_url: str | None = None,
        *,
        signing_key: str | None = None,
    ) -> None:
        if not api_key:
            raise ValueError("api_key is required")
        self._http = HttpClient(api_url or DEFAULT_API_URL, api_key)
        self.runs = RunsResource(self._http, signing_key)
        self.nodes = NodesResource(self._http)
        self.agents = AgentsResource(self._http)

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> "Invariance":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()
