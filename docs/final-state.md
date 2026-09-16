# Final-state verification

Task success can be judged by **expected final state**, not a single gold tool
trajectory (#105). Different valid call sequences that reach the same state
should pass the same checks.

Tool-Semantics never auto-executes discovered MCP tools to obtain state.
Observed state must be supplied by the caller (fixtures, harnesses, or a
trusted external executor).

## Schema

On each `Probe`:

| Field | Meaning |
| --- | --- |
| `expected_state` | Deterministic key → value expectations |
| `observed_state` | Optional **fixture-only** observed map embedded in the probe file |

Or pass a JSON file to the CLI:

```bash
tool-semantics probe snap.json --probes suite.json \
  --observed-states observed.json
```

`observed.json` shape:

```json
{
  "create-issue-task": {
    "issue_open": true,
    "labels": ["bug"]
  }
}
```

## Scoring axes

Each probe result reports separately:

| Field | Meaning |
| --- | --- |
| `tool_call_correct` | Offline: expected tool/params present; model: selection + args |
| `trajectory_correct` | Single-step today mirrors tool selection; multi-step later (#108) |
| `final_state_correct` | All `expected_state` keys matched observed values |
| `final_state` | Per-key checks, partial success, failure messages |

Partial success: some keys match, others do not (`final_state.partial=true`).
Failures name the keys that did not hold.

## Library

```python
from tool_semantics.probes import Probe, ProbeKind, evaluate_probes
from tool_semantics.state_verifier import verify_final_state

probe = Probe(
    id="create-issue-task",
    intent="open a bug issue",
    kind=ProbeKind.POSITIVE,
    expected_tool="create_issue",
    expected_state={"issue_open": True, "labels": ["bug"]},
)

# Fixture observed state (CI / offline)
report = evaluate_probes(
    snapshot,
    [probe],
    observed_states={"create-issue-task": {"issue_open": True, "labels": ["bug"]}},
)

# Or verify directly
result = verify_final_state(
    {"issue_open": True},
    {"issue_open": True, "extra": "ignored"},
)
assert result.passed
```

## Eval / reports

Offline and model probe reports include the three correctness axes. When
`tool-semantics eval` (#76) is available, probe sections surface the same
`final_state` payloads from the probe gate.

## Non-goals

- Requiring exact gold trajectories
- Auto-executing destructive MCP tools unless an external harness explicitly does so
