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
    parent_run_id: str | None
    fork_point_node_id: str | None
    replay_seed: str | None
    total_input_tokens: int
    total_output_tokens: int
    total_cache_read: int
    total_cache_write: int
    total_cost_usd: float
    llm_call_count: int
    tool_call_count: int
    error_count: int
    total_latency_ms: int


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


# ── Workflow cases / events / definitions ─────────────────────────────────


CaseStatus = Literal["open", "closed"]
WorkflowEventActorType = Literal[
    "human", "agent", "llm", "service", "integration", "policy", "system"
]
EvidenceRefKind = Literal[
    "run", "node", "ticket", "doc", "slack", "github", "meeting", "url", "external"
]
WorkflowFieldType = Literal[
    "string", "number", "boolean", "datetime", "url", "currency_usd", "enum"
]
WorkflowOutcomeKind = Literal["success", "failure", "neutral"]


class Case(TypedDict):
    id: str
    agent_id: str
    tenant_id: str | None
    end_user_id: str | None
    workflow_key: str
    status: CaseStatus
    outcome: str | None
    outcome_value_usd: float | None
    owner: str | None
    custom_attrs: dict[str, Any]
    opened_at: str
    closed_at: str | None
    created_at: str
    updated_at: str


class CaseList(TypedDict):
    data: list[Case]
    next_cursor: str | None


class WorkflowEvidenceRef(TypedDict, total=False):
    kind: EvidenceRefKind
    id: str
    url: str
    label: str
    metadata: dict[str, Any]


class WorkflowEvent(TypedDict):
    id: str
    case_id: str
    agent_id: str
    tenant_id: str | None
    end_user_id: str | None
    type: str
    actor_type: WorkflowEventActorType | None
    actor_id: str | None
    payload: dict[str, Any]
    evidence_node_ids: list[str]
    evidence_refs: list[WorkflowEvidenceRef]
    idempotency_key: str | None
    occurred_at: str
    created_at: str


class WorkflowEventList(TypedDict):
    data: list[WorkflowEvent]
    next_cursor: str | None


class WorkflowDefinitionField(TypedDict, total=False):
    name: str
    label: str
    type: WorkflowFieldType
    required: bool
    enum: list[str]
    description: str


class WorkflowDefinitionStep(TypedDict, total=False):
    type: str
    label: str
    required: bool
    description: str


class WorkflowDefinitionOutcome(TypedDict, total=False):
    value: str
    label: str
    kind: WorkflowOutcomeKind


class WorkflowMetricWidget(TypedDict, total=False):
    kind: Literal["count", "sum_field", "avg_field"]
    label: str
    event_type: str
    field: str


class WorkflowDefinition(TypedDict):
    key: str
    agent_id: str
    display_name: str
    description: str | None
    expected_fields: list[WorkflowDefinitionField]
    expected_steps: list[WorkflowDefinitionStep]
    allowed_outcomes: list[WorkflowDefinitionOutcome]
    custom_metrics: list[WorkflowMetricWidget]
    created_at: str
    updated_at: str


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


# ── Memory ─────────────────────────────────────────────────────────────────

MemorySubjectType = Literal[
    "customer", "account", "user", "policy", "workflow", "preference"
]
MemorySource = Literal[
    "agent_write", "human_write", "crm", "ticket", "policy_doc", "external_system"
]
MemoryAccessType = Literal["read", "write"]
MemoryDivergenceKind = Literal[
    "stale_memory",
    "contradicted_memory",
    "unsupported_memory",
    "overgeneralized_memory",
    "memory_used_without_source",
    "memory_caused_bad_action",
    "memory_not_updated_after_ground_truth_change",
]
MemoryDivergenceStatus = Literal["open", "dismissed", "resolved"]
EvidenceRefKind = Literal["node", "tool_call", "llm_call", "document", "system_record"]


class EvidenceRef(TypedDict, total=False):
    kind: EvidenceRefKind
    id: str
    uri: str
    excerpt: str


class MemoryRecord(TypedDict):
    id: str
    agent_id: str
    subject_type: MemorySubjectType
    subject_id: str
    claim: str
    value: Any
    source: MemorySource
    confidence: float
    valid_from: str
    valid_until: str | None
    last_verified_at: str | None
    superseded_by: str | None
    provenance: list[EvidenceRef]


class MemoryAccess(TypedDict):
    id: str
    run_id: str
    node_id: str
    agent_id: str
    access_type: MemoryAccessType
    subject_type: MemorySubjectType
    subject_id: str
    key: str
    value: Any
    used_for: str
    source_node_id: str | None
    timestamp: str


class MemoryReadResponse(TypedDict):
    access: MemoryAccess
    record: MemoryRecord | None


class MemoryWriteResponse(TypedDict):
    access: MemoryAccess
    record: MemoryRecord


# ── Evals ──────────────────────────────────────────────────────────────────

EvalStatus = Literal["pass", "fail"]


class EvalMetadata(TypedDict, total=False):
    suite: str
    case: str
    expected: Any
    inputs: Any
    tags: list[str]


class EvalResult(TypedDict):
    run_id: str
    suite: str
    case: str
    status: EvalStatus
    findings: list[Finding]


class EvalCaseRecord(TypedDict):
    run_id: str
    case: str
    status: EvalStatus
    created_at: str


class EvalListResponse(TypedDict):
    suite: str
    runs: list[EvalCaseRecord]
    next_cursor: str | None


class EvalSummary(TypedDict):
    suite: str
    total: int
    passed: int
    failed: int


# Datasets / Scorers / Suites / Cases / EvalRuns / Results — mirror api-types.

EvalScorerKind = Literal["assertion", "code", "llm", "builtin"]
EvalResultStatus = Literal["passed", "failed", "errored"]
EvalSuiteRunStatus = Literal[
    "queued", "running", "succeeded", "failed", "errored"
]
EvalTargetType = Literal["agent", "recipe", "replay"]


class EvalDataset(TypedDict):
    id: str
    agent_id: str
    name: str
    description: str
    metadata: dict[str, Any]
    created_at: str
    updated_at: str


class EvalDatasetExample(TypedDict):
    id: str
    dataset_id: str
    agent_id: str
    input: dict[str, Any]
    expected: dict[str, Any]
    metadata: dict[str, Any]
    created_at: str
    updated_at: str


class EvalScorer(TypedDict):
    id: str
    agent_id: str
    name: str
    description: str
    kind: EvalScorerKind
    definition: dict[str, Any]
    metadata: dict[str, Any]
    created_at: str
    updated_at: str


class EvalSuiteRecord(TypedDict):
    id: str
    agent_id: str
    dataset_id: str | None
    name: str
    description: str
    target_type: EvalTargetType
    scorer_ids: list[str]
    metadata: dict[str, Any]
    created_at: str
    updated_at: str


class EvalCase(TypedDict):
    id: str
    suite_id: str
    agent_id: str
    dataset_example_id: str | None
    source_run_id: str | None
    source_finding_id: str | None
    source_graph_ref: str | None
    name: str
    input_bundle: dict[str, Any]
    mutations: list[dict[str, Any]]
    expected: dict[str, Any]
    assertions: list[dict[str, Any]]
    metadata: dict[str, Any]
    created_at: str
    updated_at: str


class EvalRunRecord(TypedDict):
    id: str
    suite_id: str
    agent_id: str
    target_type: EvalTargetType
    target_ref: str | None
    status: EvalSuiteRunStatus
    summary: dict[str, Any]
    started_at: str | None
    completed_at: str | None
    metadata: dict[str, Any]
    created_at: str
    updated_at: str


class EvalResultFailure(TypedDict, total=False):
    message: str
    path: str
    observed: Any
    expected: Any


class EvalResultRow(TypedDict):
    id: str
    eval_run_id: str
    case_id: str
    agent_id: str
    status: EvalResultStatus
    scores: dict[str, float]
    failures: list[EvalResultFailure]
    observed: dict[str, Any]
    expected: dict[str, Any]
    replay_run_id: str | None
    evidence: dict[str, Any]
    created_at: str
    updated_at: str


class EvalDatasetList(TypedDict):
    data: list[EvalDataset]
    next_cursor: str | None


class EvalDatasetExampleList(TypedDict):
    data: list[EvalDatasetExample]
    next_cursor: str | None


class EvalScorerList(TypedDict):
    data: list[EvalScorer]
    next_cursor: str | None


class EvalSuiteList(TypedDict):
    data: list[EvalSuiteRecord]
    next_cursor: str | None


class EvalCaseList(TypedDict):
    data: list[EvalCase]
    next_cursor: str | None


class EvalResultRowList(TypedDict):
    data: list[EvalResultRow]
    next_cursor: str | None


# Experiment + Compare — finalized backend types.

ScorerName = Literal[
    "exact_match", "contains", "numeric_tolerance", "json_match", "levenshtein"
]


class ScorerSpec(TypedDict, total=False):
    name: ScorerName
    config: dict[str, Any]


class ExperimentRunRequest(TypedDict, total=False):
    scorer_specs: list[ScorerSpec]
    baseline_run_id: str


class ScoreDelta(TypedDict):
    scorer: ScorerName
    baseline: float | None
    current: float
    delta: float


class CaseScoreDelta(TypedDict):
    case_id: str
    scores: list[ScoreDelta]


class CompareResponse(TypedDict):
    run_id: str
    baseline_run_id: str
    aggregate: list[ScoreDelta]
    cases: list[CaseScoreDelta]


class BuiltinScorer(TypedDict, total=False):
    name: ScorerName
    description: str
    config_schema: dict[str, Any]


class BuiltinScorerList(TypedDict):
    data: list[BuiltinScorer]


# ── Operational Graph ────────────────────────────────────────────────────────

GuardrailMode = Literal["suggested", "shadow", "active_monitor"]
GuardrailStatus = Literal[
    "suggested", "accepted", "shadow", "active_monitor", "rejected"
]


class OperationalEntity(TypedDict, total=False):
    id: str
    run_id: str | None
    kind: str
    source: str
    external_id: str | None
    title: str
    attributes: dict[str, Any]
    created_at: str


class OperationalEdgeProvenance(TypedDict, total=False):
    method: str
    source_artifacts: list[str]
    matching_features: list[str]
    alternatives: list[str]
    risk_impact: Literal["none", "low", "medium", "high", "critical"]


class OperationalEdge(TypedDict, total=False):
    id: str
    run_id: str
    source_id: str
    target_id: str
    kind: str
    confidence: float
    evidence_node_ids: list[str]
    provenance: OperationalEdgeProvenance
    recipe_id: str | None
    created_at: str


class OperationalFindingEvidence(TypedDict):
    label: str
    ref: str
    type: Literal["trace", "system", "doc", "history", "human"]


class RecommendedGuardrail(TypedDict):
    title: str
    rule: str
    mode: GuardrailMode


class OperationalFinding(TypedDict, total=False):
    id: str
    run_id: str
    severity: Severity
    title: str
    summary: str
    affected_entity_ids: list[str]
    evidence_node_ids: list[str]
    evidence: list[OperationalFindingEvidence]
    missing_control: str | None
    recommended_guardrail: RecommendedGuardrail | None
    status: Literal["open", "acknowledged", "resolved", "rejected"]
    created_at: str


class OperationalGraphCompleteness(TypedDict):
    business_object_linked: bool
    policy_context_found: bool
    owner_found: bool
    approval_context_found: bool
    downstream_state_change_found: bool
    score: float


class OperationalGraphResponse(TypedDict):
    run_id: str
    entities: list[OperationalEntity]
    edges: list[OperationalEdge]
    findings: list[OperationalFinding]
    completeness: OperationalGraphCompleteness


# ── Recipes & Guardrails ─────────────────────────────────────────────────────


class Recipe(TypedDict):
    id: str
    slug: str
    title: str
    domain: str
    description: str
    control: str
    rule: str
    default_mode: GuardrailMode
    enabled: bool
    builtin: bool
    created_at: str
    updated_at: str


class RecipeList(TypedDict):
    data: list[Recipe]
    next_cursor: str | None


class Guardrail(TypedDict):
    id: str
    agent_id: str
    recipe_id: str | None
    finding_id: str | None
    title: str
    rule: str
    mode: GuardrailMode
    status: GuardrailStatus
    monitor_id: str | None
    created_at: str
    updated_at: str


class GuardrailList(TypedDict):
    data: list[Guardrail]
    next_cursor: str | None


# ── Operators ──────────────────────────────────────────────────────────────

OperatorType = Literal["agent", "human"]


class Operator(TypedDict, total=False):
    id: str
    name: str
    public_key: str | None
    project_id: str
    created_at: str
    operator_type: OperatorType


class OperatorMeResponse(TypedDict, total=False):
    operator: Operator
    api_key: ApiKeyPublic


class CreateOperatorResponse(TypedDict):
    agent: Operator
    api_key: ApiKeyWithRaw


class OperatorList(TypedDict):
    data: list[Operator]
    next_cursor: str | None


# ── Agent Sessions ─────────────────────────────────────────────────────────

AgentSessionSource = Literal[
    "anthropic_sdk",
    "openai_sdk",
    "invariance_cli",
    "mcp",
    "claude_code",
    "codex_cli",
    "screen_recording",
    "microphone",
    "meeting",
    "granola_note",
    "manual_note",
    "api",
    "other",
]

AgentSessionType = Literal["coding", "review", "meeting", "note", "recording", "other"]


class AgentSession(TypedDict, total=False):
    id: str
    project_id: str
    operator_id: str | None
    agent_id: str | None
    source: AgentSessionSource
    session_type: AgentSessionType | None
    title: str | None
    external_session_id: str | None
    model: str | None
    cwd: str | None
    status: str
    created_at: str
    updated_at: str | None
    ended_at: str | None


class AgentSessionList(TypedDict):
    data: list[AgentSession]
    next_cursor: str | None


class CreateAgentSessionResponse(TypedDict):
    session: AgentSession


class AppendEventsResponse(TypedDict):
    appended: int


# ── Operational Context ────────────────────────────────────────────────────


class SystemRecord(TypedDict):
    source: MemorySource
    external_id: str
    fetched_at: str
    fields: dict[str, Any]


class OperationalContext(TypedDict, total=False):
    metadata: dict[str, Any]
    custom_fields: dict[str, Any]
    type: str
    memory_reads: list[MemoryAccess]
    memory_writes: list[MemoryAccess]
    authoritative_records: list[SystemRecord]


# --- Cortex jobs (generic evals, counterfactuals, attribution) ---------

CortexJobKind = Literal[
    "workflow_eval",
    "counterfactual_eval",
    "workflow_experiment",
    "outcome_attribution",
    "recommendation_impact_eval",
    "prompt_variant_eval",
    "policy_eval",
    "divergence_error_tracking",
    "complex_query",
]

CortexTargetType = Literal[
    "run",
    "case",
    "workflow",
    "step",
    "agent",
    "prompt",
    "policy",
    "recommendation",
    "external",
    "finding",
    "review",
    "eval_run",
    "project",
]

# How a launched job runs: ``sync`` blocks and returns the result; ``async``
# enqueues.
CortexLaunchMode = Literal["sync", "async"]

CortexJobStatus = Literal[
    "queued",
    "leased",
    "running",
    "succeeded",
    "failed",
    "dead",
    "cancelled",
]

# Terminal lifecycle states — a job is done when it reaches one of these.
CORTEX_TERMINAL_STATUSES: tuple[CortexJobStatus, ...] = (
    "succeeded",
    "failed",
    "dead",
    "cancelled",
)


class CortexJob(TypedDict, total=False):
    id: str
    status: CortexJobStatus
    job_kind: CortexJobKind
    target_type: CortexTargetType
    target_ref: str
    project_id: str
    created_at: str
    updated_at: str
    error: str | None


class CreateCortexJobResponse(TypedDict):
    job_id: str
    status: CortexJobStatus
    deduplicated: bool


class CortexCriterionResult(TypedDict, total=False):
    criterion: str
    passed: bool
    evidence_refs: list[str]
    notes: str


class WorkflowEvalResult(TypedDict, total=False):
    kind: Literal["workflow_eval"]
    passed: bool
    score: float
    criteria_results: list[CortexCriterionResult]
    findings: list[Any]
    confidence: float


class CounterfactualEvalResult(TypedDict, total=False):
    kind: Literal["counterfactual_eval"]
    answer: str
    observed_outcome: str
    hypothetical_change: str
    estimated_outcome: str
    estimated_impact: dict[str, Any]
    assumptions: list[str]
    evidence_refs: list[str]
    confidence: float
    uncertainty: str


class OutcomeAttributionFactor(TypedDict, total=False):
    factor: str
    impact: str
    evidence_refs: list[str]


class OutcomeAttributionResult(TypedDict, total=False):
    kind: Literal["outcome_attribution"]
    outcome: str
    primary_factors: list[OutcomeAttributionFactor]
    confidence: float


class DivergenceTopError(TypedDict, total=False):
    """One high-frequency error surfaced by a ``divergence_error_tracking`` job."""

    run_id: str
    kind: str
    severity: str
    status: str
    title: str
    summary: str
    suggested_action: str | None


class DivergenceErrorTrackingResult(TypedDict, total=False):
    kind: Literal["divergence_error_tracking"]
    target_type: CortexTargetType
    target_ref: str
    total_divergences: int
    open_divergences: int
    critical_open_divergences: int
    by_kind: dict[str, int]
    by_severity: dict[str, int]
    by_status: dict[str, int]
    affected_run_ids: list[str]
    top_errors: list[DivergenceTopError]
    recommended_actions: list[str]


class ComplexQueryResult(TypedDict, total=False):
    """Result of the read-only ``complex_query`` analyst.

    Every id in ``evidence_refs`` and ``affected_entities`` was observed through
    a governed read tool — the runtime fails closed against fabricated or
    cross-project ids.

    Defined locally pending an export from the shared api-types.
    """

    kind: Literal["complex_query"]
    short_answer: str
    reasoning_plan: list[str]
    evidence_refs: list[str]
    affected_entities: list[str]
    confidence: float
    restricted_evidence_count: int
    recommended_action: str
    follow_up_questions: list[str]


# Discriminated by ``kind``. Stored as a generic dict on the response so
# callers can branch without runtime parsing; static checkers see the union.
CortexJobResultPayload = (
    WorkflowEvalResult
    | CounterfactualEvalResult
    | OutcomeAttributionResult
    | DivergenceErrorTrackingResult
    | ComplexQueryResult
)


class CortexJobResult(TypedDict, total=False):
    job_id: str
    status: CortexJobStatus
    result: CortexJobResultPayload
    error: str | None


class LaunchCortexJobResponse(TypedDict, total=False):
    """Response from ``POST /v1/cortex/jobs/launch``.

    For ``sync`` launches the parsed ``result`` (or ``error``) is embedded once
    the job ran; ``async`` launches return the queued job — poll
    ``wait_for_result``.
    """

    job_id: str
    status: CortexJobStatus
    mode: CortexLaunchMode
    deduplicated: bool
    result: CortexJobResultPayload
    error: str | None


class RetryCortexJobResponse(TypedDict):
    job_id: str
    status: CortexJobStatus


class CortexJobRun(TypedDict, total=False):
    """One attempt at running a job (the ``cortex_job_runs`` audit-trail row)."""

    id: str
    job_id: str
    project_id: str
    job_kind: CortexJobKind
    prompt_spec_id: str | None
    prompt_key: str | None
    prompt_version: int | None
    model: str | None
    status: Literal["running", "succeeded", "failed", "cancelled"]
    output_refs: dict[str, Any]
    metrics: dict[str, Any]
    error: str | None
    started_at: str
    finished_at: str | None
    latency_ms: int | None


class ListCortexJobRunsResponse(TypedDict):
    runs: list[CortexJobRun]


# ── Divergences ──────────────────────────────────────────────────────────────

DivergenceKind = Literal[
    "intent",
    "policy",
    "workflow",
    "context",
    "outcome",
    "behavior_drift",
    "memory_consistency",
]
DivergenceStatus = Literal[
    "open", "accepted", "dismissed", "converted_to_monitor"
]


class Divergence(TypedDict):
    id: str
    agent_id: str
    run_id: str
    kind: DivergenceKind
    severity: Severity
    title: str
    summary: str
    expected: dict[str, Any]
    observed: dict[str, Any]
    evidence: dict[str, Any]
    suggested_action: str | None
    confidence: float
    status: DivergenceStatus
    created_at: str
    updated_at: str


class DivergenceList(TypedDict):
    data: list[Divergence]
    next_cursor: str | None


# ── Saved views / queries ────────────────────────────────────────────────────

QuerySource = Literal["executions", "events", "runs", "nodes", "captures"]
QueryAggregation = Literal[
    "count", "sum", "avg", "min", "max", "count_distinct"
]
QueryFilterOp = Literal["eq", "neq", "in", "gt", "gte", "lt", "lte"]
DashboardViz = Literal["table", "metric", "bar", "line", "list"]
SavedViewVisibility = Literal["agent", "private"]


class QueryFilter(TypedDict, total=False):
    field: str
    op: QueryFilterOp
    value: str | int | float | bool | list[Any] | None


class QuerySpec(TypedDict, total=False):
    fields: list[str]
    filters: list[QueryFilter]
    group_by: str
    aggregation: QueryAggregation
    aggregation_field: str
    order_by: str
    order_dir: Literal["asc", "desc"]
    limit: int


class SavedView(TypedDict):
    id: str
    agent_id: str
    name: str
    source: QuerySource
    spec: QuerySpec
    viz: DashboardViz
    visibility: SavedViewVisibility
    created_at: str
    updated_at: str


class SavedViewList(TypedDict):
    data: list[SavedView]


class QueryResultGroup(TypedDict):
    key: str | int | float | None
    value: float


class QueryResult(TypedDict, total=False):
    source: QuerySource
    scalar: float
    groups: list[QueryResultGroup]
    rows: list[dict[str, Any]]
    row_count: int
    truncated: bool


# ── External receipts ────────────────────────────────────────────────────────

ExternalReceiptSource = Literal[
    "stripe",
    "zendesk",
    "salesforce",
    "hubspot",
    "slack",
    "linear",
    "jira",
    "webhook",
    "jsonl",
    "csv",
    "custom",
]


class ExternalReceipt(TypedDict):
    id: str
    agent_id: str
    run_id: str | None
    node_id: str | None
    source: ExternalReceiptSource
    kind: str
    external_id: str | None
    occurred_at: str | None
    business_object_type: str | None
    business_object_id: str | None
    subject_type: str | None
    subject_id: str | None
    correlation_keys: dict[str, str]
    payload: dict[str, Any]
    metadata: dict[str, Any]
    hash: str
    created_at: str
    updated_at: str


class ExternalReceiptList(TypedDict):
    data: list[ExternalReceipt]
    next_cursor: str | None


# ── Metrics ──────────────────────────────────────────────────────────────────


class OverviewMetricsTotals(TypedDict):
    runs: int
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cost_usd: float
    llm_calls: int
    tool_calls: int
    errors: int


class OverviewMetricsSeriesPoint(TypedDict):
    bucket: str
    cost_usd: float
    tokens: int
    llm_calls: int


class OverviewMetricsByPlatform(TypedDict):
    platform: str
    run_count: int
    total_cost_usd: float


class OverviewMetrics(TypedDict):
    window_hours: int
    totals: OverviewMetricsTotals
    success_rate: float
    avg_latency_ms: float
    series: list[OverviewMetricsSeriesPoint]
    by_platform: list[OverviewMetricsByPlatform]


# Per-agent usage rows from /v1/metrics/agents — backend shape is loose, so
# model as plain dicts to avoid drift when columns are added.
AgentUsage = dict[str, Any]


# ── Workflow observability ───────────────────────────────────────────────────

WorkflowHealthStatus = Literal["healthy", "degraded", "stale", "failed"]


class WorkflowObservabilityRollup(TypedDict):
    workflow_key: str
    execution_count: int
    open_count: int
    closed_count: int
    stale_open_count: int
    missing_outcome_count: int
    failed_run_count: int
    node_error_count: int
    event_count: int
    run_count: int
    capture_count: int
    node_count: int
    executions_with_events: int
    executions_with_runs: int
    executions_with_captures: int
    executions_with_nodes: int
    total_cost_usd: float
    total_input_tokens: int
    total_output_tokens: int
    avg_duration_ms: float | None
    first_seen_at: str | None
    last_seen_at: str | None


class WorkflowObservabilityRollupList(TypedDict):
    data: list[WorkflowObservabilityRollup]
    next_cursor: None


class WorkflowExecutionEvidenceMix(TypedDict):
    events: bool
    runs: bool
    captures: bool
    nodes: bool


class WorkflowExecutionHealth(TypedDict):
    case_id: str
    workflow_key: str
    status: CaseStatus
    opened_at: str
    closed_at: str | None
    last_seen_at: str | None
    stale: bool
    health: WorkflowHealthStatus
    reasons: list[str]
    event_count: int
    run_count: int
    capture_count: int
    node_count: int
    error_count: int
    total_cost_usd: float
    total_tokens: int
    evidence_mix: WorkflowExecutionEvidenceMix


class WorkflowExecutionHealthList(TypedDict):
    data: list[WorkflowExecutionHealth]
    next_cursor: None
