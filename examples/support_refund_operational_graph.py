"""Capture a support-refund run, then read its operational graph.

The operational graph reconstructs the business object (the refund), the
policy / approval context, the owner, and any downstream state change from
the captured trace — plus a completeness score and findings for missing
controls. See MVP spec §4.

    export INVARIANCE_API_KEY=inv_live_...
    python examples/support_refund_operational_graph.py
"""

from invariance import Invariance

inv = Invariance()  # reads INVARIANCE_API_KEY

# Operational metadata lets the graph link the run to the business object,
# the customer, the ticket, and the approval that authorized the refund.
op_metadata = {
    "customer_id": "cus_demo_123",
    "ticket_id": "zdk_998877",
    "policy_id": "refund-under-50-no-approval",
    "approval_id": "appr_demo_456",
}

with inv.runs.start(name="support-refund", metadata=op_metadata) as run:
    with run.step("lookup_ticket", input={"ticket_id": op_metadata["ticket_id"]}) as s:
        s.output = {"reason": "duplicate charge", "amount_usd": 42.0}

    run.step(
        "stripe.refunds.create",
        type="tool_call",
        input={"charge": "ch_demo_789", "amount_usd": 42.0},
        output={"refund_id": "re_demo_001", "status": "succeeded"},
        metadata=op_metadata,
    )

# Fetch the reconstructed operational graph for the run we just captured.
graph = inv.runs.operational_graph(run.run_id)

print(f"\nOperational graph for run {graph['run_id']}")
print(f"  completeness score: {graph['completeness']['score']:.2f}")

print(f"\n  entities ({len(graph['entities'])}):")
for ent in graph["entities"]:
    print(f"    - [{ent['kind']}] {ent['title']} (source={ent['source']})")

print(f"\n  edges ({len(graph['edges'])}):")
for edge in graph["edges"]:
    print(f"    - {edge['source_id']} --{edge['kind']}--> {edge['target_id']} "
          f"(confidence={edge['confidence']:.2f})")

print(f"\n  findings ({len(graph['findings'])}):")
for finding in graph["findings"]:
    print(f"    - [{finding['severity']}] {finding['title']}")
    print(f"      {finding['summary']}")
    for ev in finding.get("evidence", []):
        print(f"      evidence: {ev['label']} ({ev['type']}) -> {ev['ref']}")
    rec = finding.get("recommended_guardrail")
    if rec:
        print(f"      recommended guardrail [{rec['mode']}]: {rec['title']} — {rec['rule']}")
