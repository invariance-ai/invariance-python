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

After the run completes, inspect it from any terminal:

```bash
inv runs inspect <run_id> --json   # full run + nodes, agent-friendly
inv nodes tail <run_id>            # stream nodes as they arrive
```

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
