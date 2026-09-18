# Stateful multi-step workflow evaluation (#108)

Evaluate multi-step agent tasks where **final state** is the strongest success
criterion. Intermediate checkpoints are diagnostics; alternate valid
trajectories can still pass.

## Concepts

| Level | Meaning |
| --- | --- |
| **Task** | Final expected state matched (`state_contains` semantics) |
| **Trajectory** | Tool sequence matches an `allowed_trajectories` entry (optional) |
| **Tool** | Fraction of checkpoint `required_tools` observed in the trace |

Dead ends (`dead_end=true`) and recoveries (`recovered=true`) on steps are
counted in the report without automatically failing a task that reaches the
correct final state.

## Fixture model (no live MCP)

```python
from tool_semantics.workflows import (
    WorkflowCheckpoint,
    WorkflowStep,
    WorkflowTask,
    WorkflowTrace,
    evaluate_workflow,
    evaluate_workflows,
    render_workflow_report_markdown,
)

task = WorkflowTask(
    id="triage-bug",
    intent="Find a bug and comment",
    initial_state={"issue": None, "commented": False},
    final_state={"issue": {"number": 42}, "commented": True},
    checkpoints=[
        WorkflowCheckpoint(id="found", required_tools=["search_issues"]),
    ],
    allowed_trajectories=[
        ["search_issues", "create_comment"],
        ["list_issues", "get_issue", "create_comment"],
    ],
)

trace = WorkflowTrace(
    task_id="triage-bug",
    steps=[
        WorkflowStep(
            tool="list_issues",
            state_patch={"issue": {"number": 42, "state": "open"}},
        ),
        WorkflowStep(tool="get_issue"),
        WorkflowStep(tool="create_comment", state_patch={"commented": True}),
    ],
)

result = evaluate_workflow(task, trace)
assert result.passed  # final state wins
```

State evolves by applying each step’s `state_patch` (deep merge). You may also
set `trace.final_state` explicitly. No MCP tools are executed.

## Related

- Final-state verifier library work (#105) can later plug in as the matcher
- Trace schema / replay (#83 / #84) can supply real trajectories
