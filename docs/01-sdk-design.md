# Python SDK Design

The Python SDK mirrors the clean MVP customer loop, but can ship after the TypeScript SDK if needed.

Platform design source:

```text
../invariance-platform/docs/00-mvp-system-design.md
```

Legacy reference:

```text
../_archive/invariance-sdk-legacy/packages/python
```

## SDK Boundary

The MVP Python SDK supports:

```text
initialize client
start run
write nodes
finish/fail run
create simple monitor
evaluate monitor
list signals
list/claim/resolve reviews
```

Do not include:

- A2A
- contracts
- evals
- datasets
- ontology
- governance
- LLM judge monitors
- code monitors

## Naming

Use `run` in Python.

Backend `session_id` should be available, but the developer-facing object is a run.

Use `node`, not `trace_node`, in public API names.

## MVP API Shape

```py
from invariance import Invariance

inv = Invariance(api_key="...")

with inv.runs.start(name="support-ticket") as run:
    with run.step("tool_call", input={"query": "refund"}) as s:
        s.output = {"answer": "..."}

monitor = inv.monitors.create_simple(
    name="Dangerous output",
    evaluator={"type": "keyword", "field": "output", "keywords": ["dangerous"]},
    severity="high",
    review=True,
)

inv.monitors.evaluate(monitor["id"])

signals = inv.signals.list()
reviews = inv.reviews.list()
```

Python `review=True` maps to backend `creates_review=True`.

## Modules

```text
Invariance
  run
  monitors
  signals
  reviews
```

## Porting Notes

Useful legacy files:

```text
../_archive/invariance-sdk-legacy/packages/python/invariance/modules/run.py
../_archive/invariance-sdk-legacy/packages/python/invariance/resources/trace.py
../_archive/invariance-sdk-legacy/packages/python/invariance/resources/monitors.py
../_archive/invariance-sdk-legacy/packages/python/invariance/resources/signals.py
```

Port only the run/session ergonomics and HTTP resource ideas.

Do not port old advanced modules until the MVP dry run passes.
