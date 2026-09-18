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
| `discovery.accuracy_regression` | warning | Progressive-discovery curve: selection accuracy dropped as catalog grew (#86) |
| `tool.output_schema_added` | info | A tool gained an `outputSchema` |
| `tool.output_schema_removed` | breaking | A tool lost its `outputSchema` |
| `tool.output_schema_changed` | breaking | A tool's `outputSchema` changed (umbrella; see `output.field_*`) |
| `output.field_removed` | breaking | Object output property removed |
| `output.field_added` | info | Object output property added |
| `output.field_type_changed` | breaking | Object output property JSON Schema `type` changed |
| `output.field_renamed` | warning | Likely output field rename (deterministic confidence) |
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

Structural `compare` does **not** yet emit `behavior.*` change codes.
Model-backed probe work (#44–#47) ships separately as:

- Library APIs: `evaluate_probes_with_model`, `compute_probe_metrics`,
  `run_probe_trials` (see [probes.md](probes.md))
- Report helpers: `render_probe_metrics_*` / `render_stability_*` in `report.py`

Those results are **not** folded into `CompatibilityReport.changes` today, so
they do not affect compare exit codes by themselves.

The reserved `behavior.*` namespace (for example
`behavior.tool_selection_failed`, `behavior.arguments_invalid`,
`behavior.unstable_probe`) is **deferred**. Tracking issue:
[#61](https://github.com/askmy-stack/tool-semantics/issues/61). Until that
lands, do not invent ad-hoc behavioral codes in the diff engine; extend probe
metrics instead or implement #61 with an update to this catalog in the same PR.
