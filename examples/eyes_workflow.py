import os

from invariance import Invariance, MonitorSpec, action, on, rule


inv = Invariance(api_key=os.environ["INVARIANCE_API_KEY"])
project_id = os.environ.get("INVARIANCE_PROJECT_ID")
workflow_key = "agent.code_change"

inv.workflow_definitions.create(
    key=workflow_key,
    display_name="Agent code change",
    description="Claude Code, Codex, or SDK agent completing a repository task.",
    expected_fields=[
        {"name": "repo", "type": "string", "required": True},
        {"name": "ticket", "type": "string"},
        {"name": "agent_source", "type": "enum", "enum": ["claude_code", "codex", "sdk", "mcp"]},
    ],
    expected_steps=[
        {"type": "context", "label": "Task context", "required": True},
        {"type": "tool_call", "label": "Tool call", "required": True},
        {"type": "decision", "label": "Decision", "required": True},
    ],
    allowed_outcomes=[
        {"value": "completed", "kind": "success"},
        {"value": "needs_human_review", "kind": "neutral"},
        {"value": "failed", "kind": "failure"},
    ],
)

workflow_case = inv.cases.create(
    workflow_key=workflow_key,
    tenant_id="demo-org",
    end_user_id="demo-user",
    owner="platform-ops",
    custom_attrs={
        "repo": "invariance/platform",
        "ticket": "OBS-1",
        "agent_source": "codex",
    },
    tags=["eyes", "agent-observability"],
)

with inv.cases.with_case(workflow_case):
    with inv.runs.start(
        name="codex:instrument-observability",
        metadata={
            "repo": "invariance/platform",
            "ticket": "OBS-1",
            "agent_source": "codex",
        },
    ) as run:
        with run.step(
            "context",
            input={
                "task": "launch Eyes observability",
                "operator": "hardik",
                "repo": "invariance/platform",
            },
        ):
            pass

        with run.step(
            "tool_call",
            type="tool_call",
            input={"tool_name": "rg", "pattern": "workflow_observability"},
            custom_fields={"tool_name": "rg", "status": "success"},
        ) as step:
            step.output = {"files": ["apps/dashboard/src/pages/Eyes.tsx"]}

        with run.step(
            "decision",
            type="decision",
            input={"options": ["docs only", "ship cockpit"]},
            custom_fields={"requires_human_review": False},
        ) as step:
            step.output = {"selected": "ship cockpit"}

        run_id = run.run_id

inv.events.create(
    workflow_case["id"],
    type="instrumentation.completed",
    actor_type="agent",
    actor_id="codex",
    payload={"run_id": run_id, "workflow_key": workflow_key},
    evidence_refs=[{"kind": "run", "id": run_id, "label": "instrumented agent run"}],
    tags=["eyes"],
)

inv.monitors.create(
    MonitorSpec(
        name="Agent run requested human review",
        on=on.node(type="decision"),
        when=rule.field_equals("custom_fields.requires_human_review", True),
        do=[
            action.create_finding(
                severity="medium",
                title="Agent requested human review",
                type="human_review_needed",
            ),
            action.create_review(),
        ],
        description="Creates a review when an agent marks a decision for human review.",
    )
)

inv.saved_views.create(
    name="Task usage by action",
    source="nodes",
    spec={"group_by": "action_type", "aggregation": "count", "limit": 20},
    viz="bar",
)

inv.saved_views.create(
    name="Agent workflows by outcome",
    source="executions",
    spec={"group_by": "outcome", "aggregation": "count", "limit": 20},
    viz="bar",
)

dataset = inv.evals.datasets.create(
    name="agent-code-change-regression",
    description="Golden tasks generated from observed agent workflow traces.",
    metadata={"workflow_key": workflow_key, "source_run_id": run_id},
)

example = inv.evals.datasets.append_example(
    dataset["id"],
    input={
        "prompt": "Instrument observability for agent workflow usage.",
        "workflow_key": workflow_key,
    },
    expected={
        "assertions": [
            {"path": '$.nodes[?(@.action_type=="tool_call")]', "op": "present"},
            {"path": '$.events[?(@.type=="instrumentation.completed")]', "op": "present"},
        ]
    },
    metadata={"source_run_id": run_id, "ticket": "OBS-1"},
)

suite = inv.evals.suites.create(
    name="Agent workflow regression",
    target_type="graph",
    dataset_id=dataset["id"],
    metadata={"workflow_key": workflow_key},
)

inv.evals.cases.create(
    suite["id"],
    name="observability trace has tool usage and completion event",
    dataset_example_id=example["id"],
    source_run_id=run_id,
    expected=example["expected"],
    assertions=[
        {"path": '$.nodes[?(@.action_type=="tool_call")]', "op": "present"},
        {"path": '$.events[?(@.type=="instrumentation.completed")]', "op": "present"},
    ],
)

if project_id:
    answer = inv.cortex.ask(
        "What dashboard views should I create for agent workflow usage and human reviews?",
        project_id=project_id,
        target_type="case",
        target_ref=workflow_case["id"],
        input_refs={"run_ids": [run_id], "case_ids": [workflow_case["id"]]},
    )
    print(answer["short_answer"], answer["evidence_refs"])

inv.cases.close(workflow_case["id"], outcome="completed")
print({"case_id": workflow_case["id"], "run_id": run_id, "dataset_id": dataset["id"], "suite_id": suite["id"]})
