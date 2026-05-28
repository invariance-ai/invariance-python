"""Production run -> eval case -> suite run -> failures.

The highest-value eval workflow: pin a real (bad) production run as a
regression test, run the suite, and print what failed.

    export INVARIANCE_API_KEY=inv_test_...
    export RUN_ID=run_...
    python examples/eval_from_run.py
"""

import os
import sys

from invariance import Invariance

run_id = os.environ.get("RUN_ID")
if not run_id:
    raise SystemExit("Set RUN_ID to an existing production run id.")

inv = Invariance()  # reads INVARIANCE_API_KEY

# 1. Create the suite that holds regression cases.
suite = inv.evals.suites.create(name="prod-regressions", target_type="run")
print(f"suite: {suite['id']}")

# 2 + 3. Snapshot the run into a case with one structural expectation and two
# assertions (a negative finding check + a numeric completeness floor).
case = inv.evals.cases.create_from_run(
    suite["id"],
    source_run_id=run_id,
    name="refund requires finance approval",
    expected={"entities": [{"kind": "approval"}]},
    assertions=[
        {"path": "findings", "op": "not_contains", "value": {"kind": "tool_loop"}},
        {"path": "completeness.score", "op": "numeric_gte", "value": 0.6},
    ],
)
print(f"case: {case['id']}")

# 4. Run every case in the suite.
run = inv.evals.suites.run(suite["id"])
print(f"eval run: {run['id']} -> {run['status']}")
if run.get("results_url"):
    print(f"results: {run['results_url']}")

# 5. Print failures the run returns inline (no second round-trip).
failures = run.get("failures") or []
if failures:
    print("\nFailures:")
    for f in failures:
        print(f"  - [{f['case_id']}] {f.get('path', '')} {f['message']}")
    sys.exit(1)
else:
    print("\nAll cases passed.")
