from __future__ import annotations

from .client import HttpClient, InvarianceApiError, RateLimitError
from ._retry import RetryPolicy
from .config import DEFAULT_API_URL, Features, ResolvedConfig, resolve_config
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
    action,
)
from .node_types import NodeType, NodeTypesResource, define_node_type
from .signals import SignalType, SignalsResource, define_signal_type
from .proofs import ProofsResource
from .findings import FindingsResource
from .reviews import ReviewsResource
from .narratives import NarrativesResource
from .kb import KbResource
from .ask import AskResource
from .async_client import (
    AsyncAgentsResource,
    AsyncAskResource,
    AsyncFindingsResource,
    AsyncInvariance,
    AsyncKbResource,
    AsyncMonitorsResource,
    AsyncNarrativesResource,
    AsyncNodesResource,
    AsyncNodeTypesResource,
    AsyncProofsResource,
    AsyncReviewsResource,
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

__all__ = [
    "Invariance",
    "InvarianceApiError",
    "RateLimitError",
    "RetryPolicy",
    "Features",
    "ResolvedConfig",
    "resolve_config",
    "DEFAULT_API_URL",
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
    "AsyncProofsResource",
    "AsyncFindingsResource",
    "AsyncReviewsResource",
    "async_trace",
    "NodesResource",
    "AgentsResource",
    "MonitorsResource",
    "MonitorSpec",
    "compile_monitor",
    "on",
    "rule",
    "action",
    "NodeType",
    "NodeTypesResource",
    "AsyncNodeTypesResource",
    "define_node_type",
    "SignalType",
    "SignalsResource",
    "define_signal_type",
    "ProofsResource",
    "FindingsResource",
    "ReviewsResource",
    "NarrativesResource",
    "AsyncNarrativesResource",
    "KbResource",
    "AskResource",
    "AsyncKbResource",
    "AsyncAskResource",
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
        api_key: str | None = None,
        api_url: str | None = None,
        *,
        signing_key: str | None = None,
        features: dict[str, bool] | None = None,
        retry_policy: RetryPolicy | None = None,
    ) -> None:
        cfg = resolve_config(
            api_key=api_key,
            api_url=api_url,
            signing_key=signing_key,
            features=features,
        )
        self.config = cfg
        self.features = cfg.features
        self._http = HttpClient(cfg.api_url, cfg.api_key, retry_policy=retry_policy)
        self.runs = RunsResource(self._http, cfg.signing_key, features=cfg.features)
        self.nodes = NodesResource(self._http)
        self.agents = AgentsResource(self._http)
        self.monitors = MonitorsResource(self._http)
        self.signals = SignalsResource(self._http)
        self.proofs = ProofsResource(self._http)
        self.findings = FindingsResource(self._http)
        self.reviews = ReviewsResource(self._http)
        self.narratives = NarrativesResource(self._http)
        self.node_types = NodeTypesResource(self._http)
        self.kb = KbResource(self._http)
        self.ask = AskResource(self._http)

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> "Invariance":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()
