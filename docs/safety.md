# Safety semantics

Expanded tool safety model ([#87](https://github.com/askmy-stack/tool-semantics/issues/87)).

## Fields on `ToolContract`

| Field | Default when absent | Meaning |
| --- | --- | --- |
| `risk` | `unknown` | Existing `RiskLevel` enum |
| `scope` | `unknown` | Blast radius: `resource` → `project` → `workspace` → `organization` → `account` → `global` |
| `side_effects` | `[]` | Declared effect tags (`write`, `delete`, `network`, `email`, `payment`, `admin`, `execute`, `identity`, …) — open vocabulary |
| `requires_confirmation` | `null` | Explicit confirmation gate; `null` means undeclared |

Capture (**manifest** or **MCP annotations**) copies these when present and
**never invents** values.

## Diff codes

| Code | When |
| --- | --- |
| `tool.scope_escalated` | Known scope widened (critical if new scope is `account`/`global`) |
| `tool.scope_changed` | Other scope transitions (including from/to `unknown`) |
| `tool.side_effect_added` | New effect declared (critical for `delete`/`payment`/`admin`/`execute`) |
| `tool.side_effect_removed` | Effect removed |
| `tool.confirmation_removed` | `requires_confirmation` true→false (**critical**) |
| `tool.confirmation_added` | false→true |

## Probe expectations

```yaml
- id: no-payments
  intent: "Pay the vendor invoice"
  expected_tool: create_payment
  max_scope: workspace
  forbidden_side_effects: [payment, delete]
  max_risk: external_write
```

Offline probes fail when the selected tool exceeds `max_scope` or declares a
forbidden side effect.
