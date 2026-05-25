"""Coverage tripwire: every in-scope data/observability-plane resource must be
exposed on BOTH the sync ``Invariance`` and async ``AsyncInvariance`` clients.

Guards the #1 drift risk in this SDK: async resources are hand-duplicated in
``async_client.py`` and are easy to forget when a new resource lands on the
sync client. If you add an in-scope resource, add it here too.
"""

from __future__ import annotations

import pytest

from invariance import AsyncInvariance, Invariance

IN_SCOPE_RESOURCES = [
    "divergences",
    "saved_views",
    "receipts",
    "workflow_observability",
    "metrics",
    "guardrails",
    "recipes",
    "kb",
    "ask",
    "node_types",
    "narratives",
    "proofs",
    "runs",
    "nodes",
    "cases",
    "events",
    "sessions",
    "captures",
    "dna",
    "cortex",
    "monitors",
    "signals",
    "findings",
    "reviews",
    "evals",
    "agents",
    "operators",
]


@pytest.fixture(scope="module")
def sync_client() -> Invariance:
    return Invariance(api_key="inv_test", api_url="http://test.local")


@pytest.fixture(scope="module")
def async_client() -> AsyncInvariance:
    return AsyncInvariance(api_key="inv_test", api_url="http://test.local")


@pytest.mark.parametrize("attr", IN_SCOPE_RESOURCES)
def test_sync_client_exposes_resource(sync_client: Invariance, attr: str) -> None:
    assert hasattr(sync_client, attr), f"Invariance is missing .{attr}"


@pytest.mark.parametrize("attr", IN_SCOPE_RESOURCES)
def test_async_client_exposes_resource(
    async_client: AsyncInvariance, attr: str
) -> None:
    assert hasattr(async_client, attr), f"AsyncInvariance is missing .{attr}"


def test_sync_and_async_expose_same_in_scope_resources(
    sync_client: Invariance, async_client: AsyncInvariance
) -> None:
    sync_missing = [a for a in IN_SCOPE_RESOURCES if not hasattr(sync_client, a)]
    async_missing = [a for a in IN_SCOPE_RESOURCES if not hasattr(async_client, a)]
    assert sync_missing == []
    assert async_missing == []
