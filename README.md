# Invariance Python SDK

Official Python SDK for the [Invariance AI](https://invariance.ai) platform. Start runs, emit nodes, and drive the customer loop from any Python agent stack.

Part of the Invariance SDK family:

- [`invariance-sdk`](./) — Python SDK (this repo).
- [`@invariance/sdk`](../invariance-typescript) — TypeScript SDK.
- [`@invariance/cli`](../invariance-cli) — command-line interface.

## Install

Install from the GitHub repository (no PyPI release yet):

```bash
pip install "invariance-sdk @ git+https://github.com/invariance-ai/invariance-python@main"
```

Requires Python >= 3.10.

## Quickstart

```python
from invariance import Invariance

inv = Invariance(api_key="inv_live_...")  # or read from INVARIANCE_API_KEY

# Attach business identifiers at run.start so traces are queryable by
# customer / ticket / refund / order — whatever you operate on.
with inv.runs.start(
    name="refund-flow",
    metadata={"customer_id": "c_123", "ticket_id": "t_456", "refund_id": "rf_789"},
) as run:
    # Tool call: action_type is the tool name, input/output are auto-recorded
    with run.step("stripe.refunds.create", input={"order_id": order_id}) as s:
        try:
            result = stripe_refund(order_id)
            s.output = {"refund_id": result.id, "amount": result.amount}
        except Exception as exc:
            # Step records the error and re-raises; the enclosing run is
            # marked failed when the with-block exits via exception
            s.error = {"type": type(exc).__name__, "message": str(exc)}
            raise

    run.step(
        "decision",
        input={"reason": "refund issued"},
        output={"status": "completed"},
    )
```

Exiting the outer `with` block finishes the run. If the block raises, the run is marked failed automatically. To fail a run explicitly without raising:

```python
run.fail("payment provider returned 5xx")
```

After the run completes, fetch it from the SDK:

```python
fetched = inv.runs.get(run.run_id)
nodes = inv.nodes.list(run.run_id)
inspection = inv.runs.inspect(run.run_id)
print(inspection["observability"])
# {
#   "step_count": ..., "llm_call_count": ..., "tool_call_count": ...,
#   "total_input_tokens": ..., "total_output_tokens": ...,
#   "total_words_created": ...,
#   "steps": [{"node_id": ..., "action_type": ..., "kind": ...}],
# }
```

An async client is also available as `AsyncInvariance` from `invariance`. The matching CLI (`inv runs inspect`, `inv nodes tail`) lives in the [`invariance-cli`](../invariance-cli) package.

## Multi-agent

Each `Invariance(api_key=...)` is bound to a single agent — the server reads `agent_id` from the API key on every node. To trace a multi-agent system, give each agent its own key (`inv.agents.create(...)` or the dashboard) and one `Invariance` instance per process/agent.

A delegation between agents is recorded as a **handoff node**. The sender emits one with `run.handoff()`; the receiver opens its own run and links back via `parent_handoff_token`:

```python
import os

from invariance import Invariance

# ── sender (agent: planner) ─────────────────────────────────────────
planner = Invariance(
    api_key=os.environ["PLANNER_API_KEY"],
    signing_key=os.environ.get("PLANNER_SIGNING_KEY"),  # required to mint a token
)

with planner.runs.start(name="plan-and-execute") as run:
    run.log("plan ready", {"steps": steps})
    token = run.handoff(
        to_agent_id="executor",
        reason="specialist required",
        message={"steps": steps},
    )
    handoff_token = token.encode() if token else None  # None when unsigned

# ── receiver (agent: executor) ──────────────────────────────────────
executor = Invariance(api_key=os.environ["EXECUTOR_API_KEY"])

with executor.runs.start(
    name="execute-plan",
    parent_handoff_token=handoff_token,
) as run:
    run.log("executing", {"steps": steps})
    # …
```

What the platform does with this:

- The handoff node carries `handoff_from` / `handoff_to` / `handoff_reason`. The dashboard renders it as a boundary between swimlanes.
- `parent_handoff_token` populates the receiver run's `parent_run_id`, so `/v1/runs/:id/metrics?include=descendants` rolls up the whole tree.
- When both sides sign, the token is an Ed25519 attestation: the platform verifies the receiver was actually delegated to by that sender at that node hash. Unsigned runs still get the trace shape but no chain of custody.

For inline delegations within a single run (no separate sub-run), pass the same metadata to any node helper:

```python
with run.step(
    "route",
    type="handoff",
    handoff_from="router",
    handoff_to="refunds",
    handoff_reason="category=refund",
):
    pass
```

See `invariance-platform/docs/observability.md` for the swimlane / `by_agent` metrics surface.

## Lifecycle

The SDK is run-first:

1. Initialize the client (`Invariance(...)` or `AsyncInvariance(...)`).
2. Start a run.
3. Record work as **nodes** (the atomic unit written to `/v1/trace/events`).
4. Finish the run (automatic via context manager).
5. Optionally verify the proof chain.

## Eyes workflow starter

For Claude Code, Codex, MCP tools, and other tool-calling agents, use one
workflow case per user-facing task. That gives Eyes one place to join the
agent trace, workflow events, human reviews, dashboards, Cortex analysis, and
eval datasets.

The launch template is in [`examples/eyes_workflow.py`](./examples/eyes_workflow.py).
It does the full setup:

- creates a workflow definition for agent code-change tasks;
- opens a case and starts an auto-linked run;
- records context, tool calls, and decisions as searchable nodes;
- emits a workflow event with run evidence;
- creates a monitor that opens human reviews when a decision asks for one;
- persists dashboard views such as task usage by action and outcomes by workflow;
- asks Cortex for dashboard suggestions when `INVARIANCE_PROJECT_ID` is set;
- seeds an eval dataset and suite from the observed run.

The same pattern works whether the trace came from the SDK, CLI, or MCP server:
use stable `workflow_key`, `case_id`, `run_id`, `agent_source`, `repo`, and
`ticket` fields so dashboards and evals can group the work without custom joins.

## API surface

| Resource | Purpose |
| --- | --- |
| `inv.runs` | Start, list, get, inspect, verify runs. |
| `inv.nodes` | Write nodes (trace events) and list them by run. |
| `inv.monitors` | Create, update, and evaluate simple monitors. |
| `inv.signals` | List and acknowledge monitor-emitted signals. |
| `inv.findings` | Investigation records produced from signals. |
| `inv.reviews` | Claim, unclaim, and resolve reviews. |
| `inv.agents` | Identity + key registration. |
| `inv.proofs` | Proof chain verification. |
| `inv.narratives` | LLM-generated run summaries. |
| `inv.kb` | Knowledge base — `create_page` / `list_pages` / `get_page` / `update_page` / `delete_page` and `*_session` / `list_messages` / `append_message`. |
| `inv.ask` | Server-side agent loop with KB + run-context tools (`/v1/ask`). |
| `inv.memory` | Record what the agent read or wrote about a subject — `read()` / `write()` against `/v1/memory/*`. |
| `inv.evals` | Run a handler as a tracked eval case and derive pass/fail from findings — `run_case()` / `list_cases()` / `summarize()`. |
| `inv.cases` | Workflow instances — `create` / `get` / `list` / `update` / `close` / `evidence` / events + `with_case(...)`. |
| `inv.events` | Workflow events over case/run/node evidence — `list` / `list_for_case` / `create`. |
| `inv.captures` | Agent session recordings + evidence links. |
| `inv.guardrails` | Per-agent guardrail lifecycle — `list` / `get` / `create` / `update` / `promote`. |
| `inv.recipes` | Read-only registry of built-in operational checks — `list` / `get` / `update`. |
| `inv.divergences` | Detected expected-vs-observed gaps — `list` / `get` / `update`. |
| `inv.saved_views` | Persisted dashboard queries (full CRUD + `run`). |
| `inv.receipts` | External side-effect receipts — `create` / `create_batch` / `list` / `get`. |
| `inv.workflow_observability` | Read-only workflow rollups + per-execution health. |
| `inv.metrics` | Usage + cost rollups — `overview` / `agents`. |

### Eval datasets

Datasets are first-class objects under `inv.evals.datasets`. Store examples as
`input`, `expected`, and `metadata`, then attach them to suites and cases:

```python
seeded = inv.evals.seed_suite(
    name="agent-code-change-regression",
    run=True,
    rows=[
        {
            "name": "tool usage is traced",
            "input": {"prompt": "Add observability to the workflow."},
            "expected": {
                "assertions": [
                    {"path": '$.nodes[?(@.action_type=="tool_call")]', "op": "present"}
                ]
            },
            "mutations": [
                {"kind": "replace_prompt", "value": "Add observability and include tool spans."}
            ],
            "metadata": {"source_run_id": run_id},
        }
    ],
)

print(seeded["dataset_id"], seeded["suite_id"], seeded.get("eval_run", {}).get("id"))
```

Use the lower-level resource calls when you need to attach rows to an existing
dataset or suite:

```python
dataset = inv.evals.datasets.create(
    name="agent-code-change-regression",
    metadata={"workflow_key": "agent.code_change"},
)

example = inv.evals.datasets.append_example(
    dataset["id"],
    input={"prompt": "Add observability to the workflow."},
    expected={
        "assertions": [
            {"path": '$.nodes[?(@.action_type=="tool_call")]', "op": "present"}
        ]
    },
    metadata={"source_run_id": run_id},
)

suite = inv.evals.suites.create(
    name="Agent workflow regression",
    target_type="graph",
    dataset_id=dataset["id"],
)

inv.evals.cases.create(
    suite["id"],
    name="tool usage is traced",
    dataset_example_id=example["id"],
    source_run_id=run_id,
    expected=example["expected"],
)
```

Use `inv.evals.cases.create_from_run(...)` when a production run should become
a golden regression case, and `inv.evals.suites.run(...)` /
`inv.evals.eval_runs.list_results(...)` for suite execution results.

### Operations

Every operation is available on **both** `Invariance` (sync) and `AsyncInvariance`
(call with `await`). The two clients are kept in lockstep — see
[`../COVERAGE_MATRIX.md`](../COVERAGE_MATRIX.md). Reads accept an agent **or**
operator key; ops flagged **agent-key** return 403 on operator tokens.

| Operation | HTTP | Path | Auth |
| --- | --- | --- | --- |
| `divergences.list(...)` | GET | `/v1/divergences` | agent/operator |
| `divergences.get(id)` | GET | `/v1/divergences/:id` | agent/operator |
| `divergences.update(id, status=...)` | PATCH | `/v1/divergences/:id` | agent/operator |
| `saved_views.list()` | GET | `/v1/saved-views` | agent/operator |
| `saved_views.create(...)` | POST | `/v1/saved-views` | agent/operator |
| `saved_views.run(saved_view_id=... \| source=..., spec=...)` | POST | `/v1/saved-views/run` | agent/operator |
| `saved_views.get(id)` | GET | `/v1/saved-views/:id` | agent/operator |
| `saved_views.update(id, **patch)` | PATCH | `/v1/saved-views/:id` | agent/operator |
| `saved_views.delete(id)` | DELETE | `/v1/saved-views/:id` | agent/operator |
| `receipts.create(...)` | POST | `/v1/receipts` | **agent-key** |
| `receipts.create_batch(receipts)` | POST | `/v1/receipts/batch` | **agent-key** |
| `receipts.list(...)` | GET | `/v1/receipts` | agent/operator |
| `receipts.get(id)` | GET | `/v1/receipts/:id` | agent/operator |
| `workflow_observability.list()` | GET | `/v1/workflow-observability` | agent/operator |
| `workflow_observability.get(key)` | GET | `/v1/workflow-observability/:key` | agent/operator |
| `workflow_observability.executions(key)` | GET | `/v1/workflow-observability/:key/executions` | agent/operator |
| `metrics.overview(window_hours=...)` | GET | `/v1/metrics/overview` | agent/operator |
| `metrics.agents(window_hours=...)` | GET | `/v1/metrics/agents` | agent/operator |

### Data plane: divergences, saved views, receipts, observability, metrics

```python
from invariance import Invariance

inv = Invariance()  # uses INVARIANCE_API_KEY

# Triage divergences.
for dv in inv.divergences.list(status="open", severity="high")["data"]:
    inv.divergences.update(dv["id"], status="converted_to_monitor")

# Build + run a saved view (exactly one of saved_view_id OR source+spec).
view = inv.saved_views.create(
    name="Refund volume",
    source="runs",
    spec={"aggregation": "count", "filters": [{"field": "status", "op": "eq", "value": "failed"}]},
    viz="metric",
)
result = inv.saved_views.run(saved_view_id=view["id"])
print(result["scalar"])
# Ad-hoc, no persistence:
adhoc = inv.saved_views.run(source="events", spec={"limit": 20})

# Record an external side effect (requires an AGENT api key — 403 on operator tokens).
inv.receipts.create(
    source="stripe", kind="refund", run_id="run_abc",
    external_id="re_1", correlation_keys={"refund_id": "re_1"},
    payload={"amount_cents": 500},
)

# Read-only observability + metrics.
rollups = inv.workflow_observability.list()["data"]
health = inv.workflow_observability.executions("mortgage.refi")["data"]
overview = inv.metrics.overview(window_hours=168)
usage = inv.metrics.agents()
```

Saved views store structured query specs over `executions`, `events`, `runs`,
`nodes`, or `captures`. They are SQL-like in shape (`filters`, `group_by`,
`aggregation`, `order_by`, `limit`) but stored as governed JSON so the dashboard,
CLI, MCP server, and SDKs can all render the same view.

The identical surface is on `AsyncInvariance`:

```python
from invariance import AsyncInvariance

async with AsyncInvariance() as inv:
    open_divs = await inv.divergences.list(status="open")
    result = await inv.saved_views.run(source="runs", spec={"aggregation": "count"})
    await inv.receipts.create_batch([{"source": "slack", "kind": "message"}])
    overview = await inv.metrics.overview()
```

### Intelligence: KB + Ask

```python
from invariance import Invariance

inv = Invariance()  # uses INVARIANCE_API_KEY

inv.kb.create_page(
    path="wiki:auth-flow",
    title="Auth flow",
    body="Tokens are minted on /v1/auth/cli-token …",
)

reply = inv.ask.send("How does our auth flow work?")
print(reply["final_text"])  # cites [[wiki:auth-flow]] and [run:r_…]
```

Same surface is available on `AsyncInvariance` via `await inv.kb.create_page(...)` and `await inv.ask.send(...)`.

### Captures: linking evidence

```python
from invariance import Invariance

inv = Invariance()  # uses INVARIANCE_API_KEY

# Legacy run link (sets run_id, returns the capture):
inv.captures.link("cap_123", run_id="run_abc")

# Link to any evidence-graph target — target_type defaults to "run":
link = inv.captures.link(
    "cap_123", target_type="case", target_id="case_xyz", link_type="evidence"
)

links = inv.captures.list_links("cap_123")["links"]
inv.captures.unlink("cap_123", link_id=link["id"])
```

## Configuration

Resolved in priority order:

1. Explicit `Invariance(api_key=..., api_url=...)` arguments.
2. Env vars: `INVARIANCE_API_KEY`, `INVARIANCE_API_URL`.
3. Built-in defaults.

## Development

```bash
uv sync --all-extras
pytest
```

## License

MIT. See [LICENSE](./LICENSE).
