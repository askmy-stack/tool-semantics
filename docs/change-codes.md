# Change codes

Stable codes emitted by `tool_semantics.diff.compare_snapshots`.  
Severities **`breaking`** and **`critical`** fail CI (`compare` exits `1`).

| Code | Typical severity | Meaning |
| --- | --- | --- |
| `tool.removed` | breaking | A tool present in the baseline is absent in the candidate |
| `tool.added` | info | A new tool appeared; selection-collision testing is still pending |
| `tool.description_changed` | warning | Description text changed; model tool-selection may drift |
| `tool.risk_changed` | warning / critical | Declared risk level changed (critical when escalating from `read_only`) |
| `tool.renamed` | warning | Heuristic match suggests a tool was renamed (not a hard remove+add) |
| `tool.output_schema_added` | info | A tool gained an `outputSchema` |
| `tool.output_schema_removed` | breaking | A tool lost its `outputSchema` |
| `tool.output_schema_changed` | breaking | A tool's `outputSchema` changed |
| `parameter.removed` | breaking | A parameter was removed from a tool |
| `parameter.added` | info | An optional parameter was added |
| `parameter.added_required` | breaking | A required parameter was added |
| `parameter.became_required` | breaking | An optional parameter became required |
| `parameter.default_changed` | warning | Parameter `default` added, removed, or changed (does not fail CI alone) |
| `parameter.type_widened` | info | JSON Schema type became more permissive (e.g. integer→number) |
| `parameter.type_narrowed` | breaking | JSON Schema type became stricter (e.g. number→integer) |
| `parameter.type_changed` | breaking | JSON Schema type changed in a non-ranked way |
| `parameter.constraints_tightened` | warning | Additional constraints such as enums were added to a free-form field |
| `parameter.schema_changed` | breaking | Parameter JSON Schema changed (excluding `default`; non-enum or unstructured) |
| `parameter.enum_values_removed` | breaking | One or more enum values were removed |
| `parameter.enum_values_added` | info | One or more enum values were added |

## Notes for contributors

- Prefer adding a **new code** over overloading an existing one.
- Update this table in the same PR that introduces a code.

## Behavioral / model-backed signals (`behavior.*`)

Model-backed probe outcomes can be mapped to first-class `Change` entries via
`tool_semantics.behavior_codes` (#61). Attach them to a structural
`CompatibilityReport` with `merge_behavior_changes` so release policy treats
selection/arg failures like other breaking codes.

| Code | Typical severity | Meaning |
| --- | --- | --- |
| `behavior.tool_selection_failed` | breaking | Model selected the wrong tool (or a forbidden one) |
| `behavior.arguments_invalid` | breaking | Model arguments failed schema / expected-argument checks |
| `behavior.risk_expectation_failed` | breaking | Selected tool violated `max_risk` |
| `behavior.confirmation_expectation_failed` | warning | Confirmation expectation was not met |
| `behavior.unstable_probe` | warning | Selections/args varied across stability trials |
| `behavior.deterministic_failure` | breaking | Same failing outcome on every stability trial |
| `behavior.missing_data` | info | Model returned no usable tool call (never breaking alone) |
| `behavior.evaluation_failed` | warning | Runner/provider error during evaluation |

`probe` JSON reports include a `behavior_changes` array in model and stability
modes. Missing-data and skipped (unapproved) probes do **not** emit breaking
codes.

Library:

```python
from tool_semantics.behavior_codes import (
    changes_from_model_probe_report,
    changes_from_stability_report,
    merge_behavior_changes,
)

behavior = changes_from_model_probe_report(model_report)
combined = merge_behavior_changes(structural_report, behavior)
```

Related APIs: `evaluate_probes_with_model`, `run_probe_trials` ([probes.md](probes.md)).
