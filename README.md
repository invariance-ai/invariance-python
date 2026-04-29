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
