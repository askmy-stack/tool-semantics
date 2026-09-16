# Agent traces

Versioned records of real tool-calling behavior for capture and replay
([#83](https://github.com/askmy-stack/tool-semantics/issues/83), replay in #84).

## Version

Every document must include:

```json
"tool_semantics_trace_version": "1.0"
```

Unknown versions fail validation. Bump the version string when making
breaking schema changes.

## Single-step shape

Required: `intent`, `selected_tool`, `arguments`.

```json
{
  "tool_semantics_trace_version": "1.0",
  "intent": "Find open issues about MCP auth",
  "selected_tool": "search_issues",
  "arguments": { "query": "MCP auth", "repo": "askmy-stack/tool-semantics" }
}
```

## Multi-step shape

Required: root `intent` plus a non-empty `turns` array. Each turn requires
`selected_tool` and `arguments` (optional per-turn `intent`, `outcome`,
`timestamp`, `latency_ms`).

## Optional fields

| Field | Meaning |
| --- | --- |
| `id` | Stable trace id |
| `outcome` / `error` | Overall or step result |
| `model` | `{ provider, model, temperature, seed, request_id }` |
| `started_at` / `ended_at` | ISO-8601 timestamps |
| `server_name` / `snapshot_ref` | Capture provenance |
| `metadata` | Free-form extras |

## Python API

```python
from pathlib import Path
from tool_semantics.traces import (
    load_trace,
    load_traces,
    redact_trace,
    trace_json_schema,
    validate_trace,
    write_trace,
)

trace = load_trace(Path("examples/traces/github_search_issues.json"))
safe = redact_trace(trace)  # scrub secret-like argument keys
schema = trace_json_schema()
```

Validation failures raise `TraceValidationError` with field paths, e.g.
`selected_tool: Field required` or a clear message when both `selected_tool`
and `turns` are missing.

## Redaction

Do **not** commit raw traces that contain tokens, passwords, or API keys.
Before sharing or checking in:

1. Prefer omitting secrets from captured arguments entirely.
2. Or call `redact_trace()` / `redact_mapping()` — keys matching
   `secret|token|password|api[_-]?key|authorization|credential|cookie`
   become `***REDACTED***` (same rules as snapshot redaction).

Example: `examples/traces/github_multi_step.json` includes a placeholder
`api_token` field to demonstrate redaction in tests; treat it as fictional.

## Examples

| File | Kind |
| --- | --- |
| `examples/traces/github_search_issues.json` | Single-step success |
| `examples/traces/github_multi_step.json` | Two-turn workflow |

## JSON Schema

Generate the current schema with:

```python
from tool_semantics.traces import trace_json_schema
import json

print(json.dumps(trace_json_schema(), indent=2))
```

Or import `AgentTrace.model_json_schema()` directly.

## Non-goals (v1)

- OpenTelemetry import/export (future adapter)
- Replay execution (see #84)
