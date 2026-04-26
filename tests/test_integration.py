"""Integration tests against a real platform (PY-002).

Skipped unless INVARIANCE_E2E=1 and INVARIANCE_API_KEY is set. The test
drives the public Python SDK through the MVP loop against a live API.
"""
from __future__ import annotations

import os
import uuid

import pytest

from invariance import Invariance, MonitorSpec, action, on, rule

pytestmark = pytest.mark.skipif(
    os.environ.get("INVARIANCE_E2E") != "1" or not os.environ.get("INVARIANCE_API_KEY"),
    reason="set INVARIANCE_E2E=1 and INVARIANCE_API_KEY to run integration tests",
)


def test_customer_dry_run_against_live_platform() -> None:
    """Run -> five nodes -> proof -> monitor -> signal/finding/review -> resolve."""
    api_key = os.environ["INVARIANCE_API_KEY"]
    api_url = os.environ.get("INVARIANCE_API_URL")
    name = f"python-e2e-{uuid.uuid4().hex[:8]}"

    with Invariance(api_key=api_key, api_url=api_url) as inv:
        with inv.runs.start(name=name, metadata={"suite": "python-e2e"}) as run:
            with run.step("context", input={"channel": "support"}):
                pass
            with run.step(
                "llm_call",
                input={"prompt": "Summarize the issue."},
                output={"answer": "The customer is asking about billing."},
            ):
                pass
            with run.step(
                "tool_call",
                input={"tool": "policy_lookup", "query": "refund policy"},
                output={"answer": "Refund requests require human review."},
            ):
                pass
            with run.step(
                "tool_call",
                input={"tool": "ticket_update"},
                output={"ok": True},
            ):
                pass
            with run.step(
                "llm_call",
                input={"prompt": "Draft reply."},
                output={"answer": "I will route this to a specialist."},
            ):
                pass

        proof = run.verify()
        assert proof["valid"] is True
        assert proof["node_count"] == 5
        assert proof["reason"] is None

        monitor = inv.monitors.create(
            MonitorSpec(
                name=f"{name}-refund-review",
                on=on.run(id=run.run_id),
                when=rule.field_contains("output.answer", "refund"),
                do=[
                    action.emit_signal(severity="high", title="Refund review required"),
                    action.create_review(),
                ],
            )
        )

        evaluated = inv.monitors.evaluate(monitor["id"], run_id=run.run_id)
        assert evaluated["execution"]["status"] == "failed"
        assert len(evaluated["execution"]["matched_node_ids"]) == 1
        assert len(evaluated["signals"]) == 1
        assert len(evaluated["findings"]) == 1
        assert len(evaluated["reviews"]) == 1

        finding = evaluated["findings"][0]
        review = evaluated["reviews"][0]
        assert finding["status"] == "review_requested"
        assert review["status"] == "pending"

        claimed = inv.reviews.claim(review["id"], notes="python e2e")
        assert claimed["status"] == "claimed"

        resolved = inv.reviews.resolve(
            review["id"],
            decision="passed",
            notes="expected monitor hit",
        )
        assert resolved["review"]["status"] == "passed"
        assert resolved["finding"]["id"] == finding["id"]
        assert resolved["finding"]["status"] == "resolved"
