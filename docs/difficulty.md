# Task difficulty and messiness (#109)

Probes and benchmarks can attach **explicit** difficulty dimensions plus an
optional `messiness` score (1–10). Reports group success rates into low /
medium / high bands without collapsing everything into one opaque number.

## Schema (`difficulty` on a probe)

| Field | Meaning |
| --- | --- |
| `tool_call_count` | Expected tool calls in a successful trajectory |
| `candidate_tool_count` | Plausible tools for the intent |
| `cross_tool_dependencies` | Needs multiple tools / namespaces |
| `stateful` | Intermediate state matters |
| `ambiguous_tool_choice` | Near-duplicate tools |
| `permission_complexity` | `0` none, `1` confirm, `2` elevated / multi-step |
| `irreversible_side_effects` | Destructive / hard to undo |
| `requires_error_recovery` | Must recover from dead ends |
| `messiness` | Optional 1–10 rollup (see bands) |
| `notes` | Free-text rationale |

### Messiness bands

| Score | Band |
| --- | --- |
| 1–3 | `low` |
| 4–6 | `medium` |
| 7–10 | `high` |

`TaskDifficulty.suggested_messiness()` derives a 1–10 hint from the dimensions;
authors should still set `messiness` explicitly when shipping fixtures.

## Example

See [`examples/probes/github_v1_with_difficulty.json`](../examples/probes/github_v1_with_difficulty.json).

```python
from tool_semantics.probes import Probe, TaskDifficulty, evaluate_probes, load_probes
from tool_semantics.difficulty import group_results_by_messiness, render_messiness_groups_markdown
from tool_semantics.scanner import capture_manifest
from pathlib import Path

snapshot = capture_manifest(Path("examples/github_server_v1.json"))
probes = load_probes(Path("examples/probes/github_v1_with_difficulty.json"))
report = evaluate_probes(snapshot, probes)
groups = group_results_by_messiness(probes, report.results)
print(render_messiness_groups_markdown(groups))
```

Offline `probe --markdown-output` includes the messiness table when probes carry
`difficulty.messiness`.
