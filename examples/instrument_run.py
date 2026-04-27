"""Minimal end-to-end run.

    export INVARIANCE_API_KEY=inv_live_...
    python examples/instrument_run.py
"""

from invariance import Invariance

inv = Invariance()  # reads INVARIANCE_API_KEY

with inv.runs.start(name="hello-invariance") as run:
    with run.step("greet", input={"who": "world"}) as s:
        s.output = {"greeting": "Hello, world!"}

    run.step("done", input={}, output={"ok": True})

print("run finished — check the dashboard")
