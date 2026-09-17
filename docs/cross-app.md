# Cross-application / multi-namespace workflows (#112)

Author tasks that span multiple tool namespaces (applications). Final state is
the primary success criterion; namespace hops and required tools are diagnostics
used for **failure attribution**.

## Concepts

| Concept | Meaning |
| --- | --- |
| `ToolNamespace` | One app catalog slice (`drive`, `gmail`, …) and its tool names |
| `CrossAppTask` | Intent, namespaces, required hop sequence, final state |
| `CrossAppTrace` | Fixture trajectory with per-step `namespace` tags |
| Attribution | Which interface change / hop likely caused a whole-workflow failure |

No live MCP tools are executed — traces are fixtures (or later, replay).

## Authoring a cross-app task

```python
from tool_semantics.cross_app import (
    CrossAppTask,
    CrossAppTrace,
    ToolNamespace,
    evaluate_cross_app,
)

task = CrossAppTask(
    id="schedule-from-drive",
    intent="Share a Drive file, email, book Calendar, log CRM",
    namespaces=[
        ToolNamespace(id="drive", tools=["drive_get_file"]),
        ToolNamespace(id="gmail", tools=["gmail_send"]),
        ToolNamespace(id="calendar", tools=["calendar_create_event"]),
        ToolNamespace(id="crm", tools=["crm_add_note"]),
    ],
    required_namespace_sequence=["drive", "gmail", "calendar", "crm"],
    namespace_required_tools={
        "drive": ["drive_get_file"],
        "gmail": ["gmail_send"],
        "calendar": ["calendar_create_event"],
        "crm": ["crm_add_note"],
    },
    final_state={
        "file_id": "file-1",
        "email_sent": True,
        "event_id": "evt-9",
        "crm_logged": True,
    },
)
```

See the full fixture:
[`examples/cross_app/drive_gmail_calendar_crm.json`](../examples/cross_app/drive_gmail_calendar_crm.json).

## Failure attribution

When the workflow fails, `attribute_failure` / `evaluate_cross_app` prefer:

1. **Namespaces with breaking/critical structural diffs** whose tools appear in
   the trace (pass `namespace_diffs={"gmail": compare_report, …}`).
2. **First namespace in the required sequence** missing required tools.
3. **Explicit `first_failed_step`** hop when the harness knows it.

Reports show attribution like ``gmail (confirmed)`` alongside pass/fail.

## Related

- Stateful single-namespace workflows (#108)
- Final-state verification (#105)
- Multi-domain corpus (#92)
