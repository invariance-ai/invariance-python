"""Create + evaluate a monitor against a run.

    export INVARIANCE_API_KEY=inv_live_...
    python examples/monitor_basics.py

What this shows:
- declare a MonitorSpec with the `on` / `rule` / `action` DSL
- create the monitor server-side via `inv.monitors.create(...)`
- run a tiny instrumented flow
- evaluate the monitor against that run
- list any findings the evaluation produced
"""

from invariance import Invariance, MonitorSpec, action, on, rule


def main() -> None:
    inv = Invariance()  # reads INVARIANCE_API_KEY

    spec = MonitorSpec(
        name="refund-amount-cap",
        description="Flag refunds over $1k for review.",
        on=on.node(type="tool_call", action_type="stripe.refunds.create"),
        when=rule.numeric("output.amount", "gt", 1000),
        do=action.create_finding(
            severity="high",
            title="Large refund issued",
            message="A refund above the $1k threshold was emitted.",
        ),
    )
    monitor = inv.monitors.create(spec)
    print(f"created monitor {monitor['id']}: {monitor['name']}")

    with inv.runs.start(name="refund-flow", metadata={"customer_id": "c_42"}) as run:
        run.step(
            "stripe.refunds.create",
            type="tool_call",
            input={"order_id": "o_1"},
            output={"refund_id": "rf_1", "amount": 1500},
        )
    print(f"finished run {run.run_id}")

    result = inv.monitors.evaluate(monitor["id"], run_id=run.run_id)
    print(f"evaluated: {result['signals_emitted']} signal(s) emitted")

    findings = inv.findings.list(limit=10)
    open_findings = [f for f in findings.get("data", []) if f.get("status") == "open"]
    print(f"open findings (latest 10): {len(open_findings)}")
    for f in open_findings[:3]:
        print(f"  - [{f.get('severity')}] {f.get('title')}")


if __name__ == "__main__":
    main()
