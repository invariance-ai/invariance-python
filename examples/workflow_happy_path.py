"""End-to-end workflow happy path.

Choose a workflow key -> open an execution -> run agent work inside it ->
emit workflow events -> capture standalone evidence -> link the capture to the
execution -> close the execution with an outcome.

    export INVARIANCE_API_KEY=inv_live_...
    python examples/workflow_happy_path.py
"""

from invariance import Invariance

inv = Invariance()  # reads INVARIANCE_API_KEY

# 1. Open one execution of a workflow type.
execution = inv.cases.create(
    workflow_key="support.escalation",
    tenant_id="acme",
    owner="support-team",
)
print("opened execution", execution["id"])

# 2. Run agent work inside the execution — runs auto-link via case_id.
with inv.cases.with_case(execution):
    with inv.runs.start(name="triage-escalation") as run:
        run.step("classify", input={}, output={"severity": "high"})

# 3. Emit a workflow event — a meaningful fact in the execution's life.
inv.cases.create_event(
    execution["id"],
    type="escalation.acknowledged",
    actor_type="human",
    actor_id="agent-jane",
    payload={"sla_minutes": 30},
)

# 4. Capture standalone evidence (e.g. a note from the customer call).
capture = inv.captures.create(
    source="manual_note",
    session_type="note",
    title="Customer call — refund expectations",
    metadata={"note": "Customer expects resolution within the day."},
)

# 5. Link the capture into the evidence graph for this execution.
inv.captures.create_link(capture["id"], case_id=execution["id"], link_type="evidence")

# 6. Close the execution with an outcome.
inv.cases.close(execution["id"], outcome="resolved", value_usd=0)

print("execution closed — open it in the dashboard to see the evidence graph")
