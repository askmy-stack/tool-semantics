# Change codes

Stable codes emitted by `tool_semantics.diff.compare_snapshots`.  
Severities **`breaking`** and **`critical`** fail CI (`compare` exits `1`).

| Code | Typical severity | Meaning |
| --- | --- | --- |
| `tool.removed` | breaking | A tool present in the baseline is absent in the candidate |
| `tool.added` | info | A new tool appeared; selection-collision testing is still pending |
| `tool.description_changed` | warning | Description text changed; model tool-selection may drift |
| `tool.risk_changed` | warning / critical | Declared risk level changed (critical when escalating from `read_only`) |
| `parameter.removed` | breaking | A parameter was removed from a tool |
| `parameter.added` | info | An optional parameter was added |
| `parameter.added_required` | breaking | A required parameter was added |
| `parameter.became_required` | breaking | An optional parameter became required |
| `parameter.schema_changed` | breaking | Parameter JSON Schema changed (non-enum or unstructured diff) |
| `parameter.enum_values_removed` | breaking | One or more enum values were removed |
| `parameter.enum_values_added` | info | One or more enum values were added |

## Notes for contributors

- Prefer adding a **new code** over overloading an existing one.
- Update this table in the same PR that introduces a code.
- Behavioral / model-based codes will land under a `behavior.*` namespace in later milestones.
