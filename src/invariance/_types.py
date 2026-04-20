"""Typed response/request shapes mirroring ``@invariance/api-types``."""

from __future__ import annotations

from typing import Any, Literal, TypedDict

Severity = Literal["info", "low", "medium", "high", "critical"]
NumericOp = Literal["gt", "gte", "lt", "lte", "eq", "neq"]


# ── Identity ───────────────────────────────────────────────────────────────


class Agent(TypedDict):
    id: str
    name: str
    public_key: str | None
    project_id: str
    created_at: str


class ApiKeyPublic(TypedDict):
    id: str
    prefix: Literal["inv_test", "inv_live"]
    label: str
    created_at: str


class ApiKeyWithRaw(ApiKeyPublic):
    key: str


class GetMeResponse(TypedDict, total=False):
    agent: Agent
    api_key: ApiKeyPublic


class CreateAgentResponse(TypedDict):
    agent: Agent
    api_key: ApiKeyWithRaw


# ── Runs ───────────────────────────────────────────────────────────────────


RunStatus = Literal["open", "completed", "failed"]


class RunModel(TypedDict):
    id: str
    agent_id: str
    name: str
    status: RunStatus
    metadata: dict[str, Any]
    created_at: str
    updated_at: str
    closed_at: str | None


# ── Nodes ──────────────────────────────────────────────────────────────────


class Node(TypedDict):
    id: str
    run_id: str
    agent_id: str
    parent_id: str | None
    action_type: str
    input: Any
    output: Any
    error: Any
    metadata: dict[str, Any]
    custom_fields: dict[str, Any]
    type: str | None
    timestamp: int
    duration_ms: int | None
    hash: str
    previous_hashes: list[str]
    signature: str | None
    created_at: str


# ── Proofs ─────────────────────────────────────────────────────────────────


RunProofReason = Literal["linkage", "hash", "signature", "missing_key"]


class RunProof(TypedDict):
    run_id: str
    valid: bool
    node_count: int
    head_hash: str | None
    first_invalid_node_id: str | None
    reason: RunProofReason | None


# ── Monitors ───────────────────────────────────────────────────────────────


ThresholdOperator = Literal[">", ">=", "<", "<=", "==", "!="]


class KeywordEvaluator(TypedDict, total=False):
    type: Literal["keyword"]
    field: str
    keywords: list[str]
    case_sensitive: bool


class ThresholdEvaluator(TypedDict):
    type: Literal["threshold"]
    field: str
    operator: ThresholdOperator
    value: float


MonitorEvaluator = KeywordEvaluator | ThresholdEvaluator


class MonitorSchedule(TypedDict, total=False):
    kind: Literal["manual", "interval"]
    every_seconds: int


class Monitor(TypedDict):
    id: str
    agent_id: str
    name: str
    description: str | None
    enabled: bool
    evaluator: MonitorEvaluator
    severity: Severity
    schedule: MonitorSchedule
    creates_review: bool
    signal_type: str | None
    last_run_at: str | None
    next_run_at: str | None
    created_at: str
    updated_at: str


class MonitorExecution(TypedDict, total=False):
    id: str
    monitor_id: str
    status: Literal["running", "passed", "failed", "error"]
    trigger: Literal["manual", "scheduled"]
    matched_node_ids: list[str]
    started_at: str
    finished_at: str | None
    error: str | None


# ── Signals ────────────────────────────────────────────────────────────────


SignalSource = Literal["monitor", "manual", "detector"]
SignalStatus = Literal["open", "acknowledged", "resolved"]


class Signal(TypedDict):
    id: str
    agent_id: str
    monitor_id: str | None
    monitor_execution_id: str | None
    run_id: str | None
    node_id: str | None
    source: SignalSource
    severity: Severity
    title: str
    message: str | None
    status: SignalStatus
    type: str | None
    data: Any
    acknowledged_at: str | None
    created_at: str


# ── Findings ───────────────────────────────────────────────────────────────


FindingStatus = Literal["open", "review_requested", "resolved", "dismissed"]


class Finding(TypedDict):
    id: str
    agent_id: str
    monitor_id: str
    signal_id: str
    run_id: str | None
    node_id: str | None
    severity: Severity
    title: str
    summary: str
    status: FindingStatus
    created_at: str
    updated_at: str


# ── Reviews ────────────────────────────────────────────────────────────────


ReviewStatus = Literal["pending", "claimed", "passed", "failed", "needs_fix"]
ReviewDecision = Literal["passed", "failed", "needs_fix"]


class Review(TypedDict):
    id: str
    agent_id: str
    finding_id: str
    status: ReviewStatus
    reviewer_agent_id: str | None
    decision: ReviewDecision | None
    notes: str | None
    created_at: str
    updated_at: str
    resolved_at: str | None


class ReviewResponse(TypedDict):
    review: Review
    finding: Finding


# ── EvaluateMonitorResponse ────────────────────────────────────────────────


class EvaluateMonitorResponse(TypedDict):
    execution: MonitorExecution
    signals: list[Signal]
    findings: list[Finding]
    reviews: list[Review]


# ── List responses ─────────────────────────────────────────────────────────


class RunList(TypedDict):
    data: list[RunModel]
    next_cursor: str | None


class NodeList(TypedDict):
    data: list[Node]
    next_cursor: str | None


class AgentList(TypedDict):
    data: list[Agent]
    next_cursor: str | None


class MonitorList(TypedDict):
    data: list[Monitor]
    next_cursor: str | None


class MonitorExecutionList(TypedDict):
    data: list[MonitorExecution]
    next_cursor: str | None


class SignalList(TypedDict):
    data: list[Signal]
    next_cursor: str | None


class FindingList(TypedDict):
    data: list[Finding]
    next_cursor: str | None


class ReviewList(TypedDict):
    data: list[Review]
    next_cursor: str | None


# ── Narratives ─────────────────────────────────────────────────────────────


NarrativeProvider = Literal["anthropic", "openai", "google"]

# Scorer used by the backend to select "interesting" nodes for synthesis.
# Kept as `str` rather than a Literal union so older SDK builds still parse
# narratives when the backend adds new scorers. Known values as of this
# release: "severity".
NarrativeScorer = str


class Narrative(TypedDict):
    run_id: str
    agent_id: str
    narrative: str
    key_moments: list[str]
    root_cause: str
    scorer: NarrativeScorer
    model: str
    provider: NarrativeProvider
    scored_node_count: int
    total_node_count: int
    created_at: str
    updated_at: str
