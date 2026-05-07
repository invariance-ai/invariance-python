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

with inv.runs.start(name="refund-flow") as run:
    with run.step("policy_lookup", input={"order_id": order_id}) as s:
        policy = lookup_policy(order_id)
        s.output = {"policy": policy}

    run.step(
        "decision",
        input={"policy": policy},
        output={"reason": "customer eligible"},
    )
```

Exiting the `with` block finishes the run. If the block raises, the run is marked failed.

An async client is also available as `AsyncInvariance` from `invariance`.

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

## API surface

| Resource | Purpose |
| --- | --- |
| `inv.runs` | Start, list, get, verify runs. |
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
