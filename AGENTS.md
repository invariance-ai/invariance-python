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

Sync (`inv.`): `runs`, `nodes`, `agents`, `monitors`, `signals`, `findings`, `reviews`, `narratives`, `node_types`, `kb`, `ask`, `memory`, `evals`, `proofs`, `recipes`, `guardrails`, `operators`, `sessions`.

`AsyncInvariance` exposes the same resources **except `recipes` and `guardrails`** — for those, use the sync client.

`OperationalContext` is a value type exported from `invariance` (not an attribute on the client); construct it directly when you need one.

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
