"""Run proofs — cryptographic verification of hash chain + signatures.

Pairs with platform route ``GET /v1/runs/:id/verify`` which re-computes
the chain and reports whether the stored state is consistent.
"""

from __future__ import annotations

from typing import Any

from .client import HttpClient


class ProofsResource:
    def __init__(self, http: HttpClient) -> None:
        self._http = http

    def verify_run(self, run_id: str) -> dict[str, Any]:
        """Return ``{valid, node_count, head_hash, first_invalid_node_id, reason}``."""
        return self._http.get(f"/v1/runs/{run_id}/verify")
