from __future__ import annotations

from .client import HttpClient, InvarianceApiError
from .runs import Run, RunsResource, Step
from .nodes import NodesResource
from .agents import AgentsResource
from .trace import trace
from .monitors import (
    MonitorsResource,
    MonitorSpec,
    compile_monitor,
    on,
    rule,
    evaluator,
    action,
)
from .node_types import NodeType, define_node_type
from .signals import SignalType, SignalsResource, define_signal_type
from .proofs import ProofsResource
from .findings import FindingsResource
from .reviews import ReviewsResource
from .async_client import (
    AsyncAgentsResource,
    AsyncInvariance,
    AsyncMonitorsResource,
    AsyncNodesResource,
    AsyncRun,
    AsyncRunsResource,
    AsyncSignalsResource,
    AsyncStep,
    async_trace,
)
from .crypto import (
    generate_keypair,
    get_public_key,
    sign_ed25519,
    verify_ed25519,
    hash_node_payload,
    stable_stringify,
    sha256_hex,
)

DEFAULT_API_URL = "https://api.useinvariance.com"

__all__ = [
    "Invariance",
    "InvarianceApiError",
    "Run",
    "RunsResource",
    "Step",
    "trace",
    "AsyncInvariance",
    "AsyncRun",
    "AsyncRunsResource",
    "AsyncStep",
    "AsyncNodesResource",
    "AsyncAgentsResource",
    "AsyncMonitorsResource",
    "AsyncSignalsResource",
    "async_trace",
    "NodesResource",
    "AgentsResource",
    "MonitorsResource",
    "MonitorSpec",
    "compile_monitor",
    "on",
    "rule",
    "evaluator",
    "action",
    "NodeType",
    "define_node_type",
    "SignalType",
    "SignalsResource",
    "define_signal_type",
    "ProofsResource",
    "FindingsResource",
    "ReviewsResource",
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
        self.monitors = MonitorsResource(self._http)
        self.signals = SignalsResource(self._http)
        self.proofs = ProofsResource(self._http)
        self.findings = FindingsResource(self._http)
        self.reviews = ReviewsResource(self._http)

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> "Invariance":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()
