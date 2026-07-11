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
- Behavioral / model-based codes will land under a `behavior.*` namespace in later milestones.
