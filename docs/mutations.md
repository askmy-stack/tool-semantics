# Mutation generator & detection metrics (#93)

Research tooling: inject **controlled regressions** into a snapshot and measure
whether Tool-Semantics **detects** them (precision / recall).

This is for methodology evaluation — not a substitute for the multi-domain
corpus (#92).

## Operators

| Kind | What it does | Expected signal |
| --- | --- | --- |
| `rename` | Renames a tool | `tool.renamed` (or remove+add) |
| `remove_tool` | Deletes a tool | `tool.removed` |
| `add_required_param` | Adds a required parameter | `parameter.added_required` |
| `confusing_twin` | Adds a near-duplicate tool | `tool.added` |
| `risk_escalation` | Sets risk to `destructive` | `tool.risk_changed` |
| `capability_drop` | Drops a `server_capabilities` key | `capability.removed` (metadata check) |

## Library

```python
from pathlib import Path
from tool_semantics.scanner import capture_manifest
from tool_semantics.mutations import run_seeded_mutations, render_detection_metrics_markdown

snap = capture_manifest(Path("examples/github_server_v1.json"))
metrics = run_seeded_mutations(snap, seed=0)
assert metrics.recall == 1.0
print(render_detection_metrics_markdown(metrics))
```

## CLI

```bash
tool-semantics mutate examples/github_server_v1.json --seed 0
tool-semantics mutate examples/github_server_v1.json --corpus benchmarks/mutations
```

Exit `1` when any seeded/corpus case is **missed**.

## Corpus folders

See [`benchmarks/mutations/`](../benchmarks/mutations/) — each case has
`before.json`, `after.json`, `expected-finding.json`.

## Research positioning

Use mutations to estimate **detection rate** under a fixed seed. Pair with the
public domain corpus (#92) for hand-authored scenarios. Do not market a single
precision number as universal model performance.
