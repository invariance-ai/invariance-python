"""Typed response/request shapes mirroring ``@invariance/api-types``."""

from __future__ import annotations

from typing import Any, Literal, TypedDict

# NotRequired is in typing only as of 3.11; project supports 3.10+, so source from typing_extensions.
from typing_extensions import NotRequired

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
    parent_run_id: str | None
    fork_point_node_id: str | None
    replay_seed: str | None
    # Server returns these only after rollups land; absent on freshly-created runs.
    # Mirrors optionality of the TS SDK Run interface.
    total_input_tokens: NotRequired[int]
    total_output_tokens: NotRequired[int]
    total_cache_read: NotRequired[int]
    total_cache_write: NotRequired[int]
    total_cost_usd: NotRequired[float]
    llm_call_count: NotRequired[int]
    tool_call_count: NotRequired[int]
    error_count: NotRequired[int]
    total_latency_ms: NotRequired[int]


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
    handoff_from: str | None
    handoff_to: str | None
    handoff_reason: str | None


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
    scope: str | None
    target: dict[str, Any] | None
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


# ── Knowledge base + Ask ───────────────────────────────────────────────────


KbPageKind = Literal["wiki", "run", "note"]
AskRole = Literal["user", "assistant", "tool"]


class KbPage(TypedDict):
    id: str
    agent_id: str
    project_id: str
    path: str
    title: str
    summary: str
    body: str
    kind: KbPageKind
    created_at: str
    updated_at: str


class KbSession(TypedDict):
    id: str
    agent_id: str
    project_id: str
    title: str
    model: str | None
    created_at: str
    updated_at: str


class KbTextBlock(TypedDict):
    type: Literal["text"]
    text: str


class KbToolUseBlock(TypedDict):
    type: Literal["tool_use"]
    id: str
    name: str
    input: Any


class KbToolResultBlock(TypedDict, total=False):
    type: Literal["tool_result"]
    tool_use_id: str
    content: str
    is_error: bool


AskContentBlock = KbTextBlock | KbToolUseBlock | KbToolResultBlock


class KbMessage(TypedDict):
    id: str
    session_id: str
    role: AskRole
    content: str | list[AskContentBlock]
    created_at: str


class KbPageList(TypedDict):
    data: list[KbPage]
    next_cursor: str | None


class KbSessionList(TypedDict):
    data: list[KbSession]
    next_cursor: str | None


class AskResponse(TypedDict):
    session: KbSession
    messages: list[KbMessage]
    final_text: str
    turns: int


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
