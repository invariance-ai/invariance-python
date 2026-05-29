# AGENTS.md

Instructions for AI coding agents that want to use `invariance-sdk` from Python.

## What this SDK does

`invariance-sdk` instruments AI agents: starts runs, emits trace nodes, drives monitors, signals, findings, evals, memory, KB. Mirrors the [TypeScript SDK](https://github.com/invariance-ai/invariance-typescript) surface. Sync + async clients, fully typed (PEP 561 `py.typed`).

## Setup (one-time, human-assisted)

A human mints the API key from the dashboard (Settings → API keys). Once set in the env, agents operate headlessly.

```bash
pip install invariance-sdk
export INVARIANCE_API_KEY=inv_live_...
```

## Agent recipe: instrument a task (sync)

```python
import os
from invariance import Invariance

inv = Invariance(api_key=os.environ["INVARIANCE_API_KEY"])

with inv.runs.start(
    name="refactor auth middleware",
    metadata={"repo": "myorg/api", "ticket": "JIRA-123",
              "user_id": "u_1", "workspace_id": "w_1"},
) as run:
    with run.step("tool_call", action_type="grep",
                  input={"pattern": "verifyToken"}) as step:
        matches = grep("verifyToken")
        step.output = {"matches": len(matches)}

    # Record a decision as its own step node.
    with run.step("decision", output={"branch": "refactor"}):
        pass

# Run is auto-finished on context-manager exit (completed on success,
# failed on exception with the error captured on the run).
# `inv.runs.get(...)` returns a Run handle (not a dict).
refetched = inv.runs.get(run.run_id)
```

Notes:
- The run id is `run.run_id` (not `run.id`).
- Per-run context belongs in `metadata=` at `runs.start(...)`; there is no `run.context(...)` method.
- There is no `run.log(...)`. Use `run.step(action_type, ...)` for every traced event. Other Run methods: `handoff()`, `signal()`, `flush()`, `finish()`, `fail()`, `verify()`.

## Default Eyes workflow for coding agents

For Claude Code, Codex, MCP tools, and SDK-based agents, prefer the Eyes
workflow template in [`examples/eyes_workflow.py`](./examples/eyes_workflow.py).
It is the default shape for launch-ready observability:

1. Create or reuse a `workflow_definitions` record for the task family.
2. Create a `cases` workflow instance with `repo`, `ticket`, `agent_source`, `tenant_id`, and `end_user_id`.
3. Start every task run inside `with inv.cases.with_case(case):` so `case_id`, `tenant_id`, and `end_user_id` are stamped automatically.
4. Emit `context`, `tool_call`, `llm_call`, `decision`, `handoff`, and `observation` nodes with small JSON payloads.
5. Emit workflow events for user-visible milestones using `inv.events.create(case["id"], ...)`.
6. Create monitors with `action.create_review()` for any condition that needs a human decision.
7. Persist saved views for usage, outcomes, review volume, and agent source coverage.
8. Ask Cortex for dashboard suggestions with `inv.cortex.ask(...)` when `INVARIANCE_PROJECT_ID` is available.
9. Promote useful tasks into runnable eval datasets with `inv.evals.seed_suite(...)`; use `inv.evals.cases.create_from_run(...)` only when you are attaching a production run to an existing suite.

Use this as the default template unless the host app already owns a stronger
workflow model.

## Agent recipe: async

```python
import asyncio, os
from invariance import AsyncInvariance

async def main():
    inv = AsyncInvariance(api_key=os.environ["INVARIANCE_API_KEY"])
    async with inv.runs.start(name="refund-flow",
                              metadata={"customer_id": "c_1"}) as run:
        async with run.step("tool_call",
                            action_type="stripe.refunds.create") as step:
            step.output = await stripe_refund(...)

asyncio.run(main())
```

## Error handling

All API failures raise `InvarianceApiError` with stable attributes (`status`, `code`, `message`, `request_id`, `details`). `code` is a server-defined string (e.g. observed in the wild: `forbidden`, `not_found`, `rate_limited`, `bad_request`, `internal_error`) — treat it as opaque and always include a fallback branch.

```python
from invariance import InvarianceApiError, RateLimitError

try:
    inv.runs.get(run_id)
except RateLimitError as err:
    # 429; internal retries already exhausted — back off further.
    ...
except InvarianceApiError as err:
    if err.status == 401 or err.code == "forbidden":
        ...  # invalid / expired key — surface to user
    elif err.status == 404 or err.code == "not_found":
        ...  # don't retry
    else:
        ...  # generic; inspect err.status / err.code / err.details
    print(err.status, err.code, err.request_id, err.details)
```

## Conventions

- **One run per user-facing task.**
- **`action_type`**: use `tool_call`, `llm_call`, `decision`, or `observation` — those are indexed by monitors.
- **Don't emit secrets.** Redact before passing to `input` / `output`.
- **Keep payloads small** (<8KB). Reference large artifacts by ID.

## Resources at a glance

Sync (`inv.`): `runs`, `nodes`, `agents`, `monitors`, `signals`, `findings`, `reviews`, `narratives`, `node_types`, `kb`, `ask`, `memory`, `evals`, `proofs`, `recipes`, `guardrails`, `operators`, `sessions`, `cases`, `events`, `captures`, `cortex`, `dna`, `divergences`, `saved_views`, `receipts`, `workflow_observability`, `metrics`.

`AsyncInvariance` exposes **every** resource above — call with `await` (e.g. `await inv.divergences.list(...)`). Sync/async parity is asserted in `tests/test_coverage.py` and tracked in [`../COVERAGE_MATRIX.md`](../COVERAGE_MATRIX.md).

`OperationalContext` is a value type exported from `invariance` (not an attribute on the client); construct it directly when you need one.

## Agent recipe: data plane (divergences, saved views, receipts, observability, metrics)

```python
# Triage divergences (expected-vs-observed gaps).
for dv in inv.divergences.list(status="open", severity="high")["data"]:
    inv.divergences.update(dv["id"], status="dismissed")

# Persist + run a dashboard query. run() takes EXACTLY ONE of
# saved_view_id OR (source, spec) — passing both/neither raises ValueError.
view = inv.saved_views.create(
    name="Failed runs", source="runs",
    spec={"aggregation": "count", "filters": [{"field": "status", "op": "eq", "value": "failed"}]},
)
print(inv.saved_views.run(saved_view_id=view["id"])["scalar"])
print(inv.saved_views.run(source="events", spec={"limit": 10})["row_count"])  # ad-hoc

# Record proof of an external side effect. create / create_batch REQUIRE an
# AGENT api key — they return 403 (InvarianceApiError, code 'forbidden') on
# operator tokens. list / get accept agent OR operator keys.
inv.receipts.create(source="stripe", kind="refund", run_id=run.run_id,
                    correlation_keys={"refund_id": "re_1"})

# Read-only health + usage.
inv.workflow_observability.list()                 # rollups across workflows
inv.workflow_observability.executions("mortgage.refi")  # per-case health
inv.metrics.overview(window_hours=168)            # default window 24h, max 2160 (90d)
inv.metrics.agents()
```

All of the above work identically on `AsyncInvariance` with `await`.

## Agent recipe: eval datasets

Create datasets from either hand-authored golden tasks or real production runs:

```python
seeded = inv.evals.seed_suite(
    name="agent-code-change-regression",
    run=True,
    rows=[
        {
            "name": "tool usage is traced",
            "input": {"prompt": "Refactor auth middleware safely."},
            "expected": {
                "assertions": [
                    {"path": '$.nodes[?(@.action_type=="tool_call")]', "op": "present"}
                ]
            },
            "metadata": {"source": "human_review"},
        }
    ],
)
```

Use lower-level calls when attaching rows to existing suites:

```python
dataset = inv.evals.datasets.create(
    name="agent-code-change-regression",
    metadata={"workflow_key": "agent.code_change"},
)

inv.evals.datasets.append_example(
    dataset["id"],
    input={"prompt": "Refactor auth middleware safely."},
    expected={
        "assertions": [
            {"path": '$.nodes[?(@.action_type=="tool_call")]', "op": "present"}
        ]
    },
    metadata={"source": "human_review"},
)

suite = inv.evals.suites.create(
    name="Agent workflow regression",
    target_type="graph",
    dataset_id=dataset["id"],
)

inv.evals.cases.create_from_run(
    suite["id"],
    source_run_id=run.run_id,
    expected={
        "assertions": [
            {"path": '$.events[?(@.type=="instrumentation.completed")]', "op": "present"}
        ]
    },
)
```

Use `metadata` to store `workflow_key`, `repo`, `ticket`, `agent_source`,
review outcome, and source run IDs. That is what lets Eyes connect production
workflow traces to regression suites later.

## Ask Cortex (read-only analyst)

`inv.cortex.ask(question, project_id=...)` runs the governed, read-only
`complex_query` analyst and returns a **cited** answer — every id in
`evidence_refs` / `affected_entities` was observed through a read tool (the
runtime fails closed against fabricated or cross-project ids). Defaults to a
synchronous, project-wide question:

```python
answer = inv.cortex.ask("Were refund SLAs met last week?", project_id="proj_123")
print(answer["short_answer"], answer["evidence_refs"])
```

Anchor on a specific entity, or enqueue and poll instead of blocking:

```python
answer = inv.cortex.ask(
    "Why did this run diverge?",
    project_id="proj_123",
    target_type="run",
    target_ref="run_1",
    mode="async",  # launch + poll; default is 'sync'
)
```

Lower-level access lives on `inv.cortex.jobs`: `launch` (governed sync/async),
`list`, `get`, `result`, `runs`, `retry`, and `wait_for_result`. The analyst
only executes when the platform's `CORTEX_TOOL_RUNTIME_ENABLED` flag is on.
`AsyncInvariance` mirrors the full surface (`await inv.cortex.ask(...)`).

## Multi-agent / handoff

```python
token = run.handoff(
    to_agent_id="agt_billing",
    message={"order_id": "o_123"},   # optional payload
    reason="needs refund authority",  # optional
    # from_agent_id defaults to the run's agent_id
)
```

Emits an Ed25519-signed handoff node so the chain of custody is verifiable end-to-end. Returns a `HandoffToken` when the SDK was initialized with `signing_key=...`; otherwise returns `None`. Deliver `token.encode()` to the receiving agent, which passes it as `parent_handoff_token=` to its own `runs.start(...)`.

## When NOT to use this SDK

- For ad-hoc shell workflows, use the [CLI](https://github.com/invariance-ai/invariance-cli) instead.
- For Claude Desktop / Cursor MCP integrations, use [`@invariance/mcp`](https://github.com/invariance-ai/invariance-mcp).

## Reference

- API surface: [`README.md`](./README.md)
- Examples: [`examples/`](./examples/)
- CLI's [`AGENTS.md`](https://github.com/invariance-ai/invariance-cli/blob/main/AGENTS.md) covers the equivalent shell flow.
