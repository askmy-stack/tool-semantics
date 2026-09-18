# Migration adapters

Declarative compatibility layer for renamed tools, argument remaps, enum
translation, and output wrappers. Use this when a breaking interface change is
intentional but callers need a bridge.

## Model

```python
from tool_semantics.adapters import (
    MigrationAdapter,
    ToolAlias,
    ArgumentMap,
    EnumMap,
    OutputWrapper,
    CompatibilityProxy,
)

adapter = MigrationAdapter(
    aliases=[ToolAlias(**{"from": "search_issues", "to": "find_work_items"})],
    arguments=[ArgumentMap(tool="find_work_items", rename={"state": "status"})],
    enums=[EnumMap(tool="find_work_items", parameter="status", values={"open": "todo"})],
    outputs=[OutputWrapper(tool="find_work_items", rename_fields={"items": "results"})],
)
proxy = CompatibilityProxy(adapter)
tool, args = proxy.route_call("search_issues", {"query": "bug", "state": "open"})
payload = proxy.route_result(tool, {"items": []})
```

## Relationship to diffs

- Diff engine may emit `tool.renamed` as a **warning** when similarity is high.
- Adapters are the **runtime** counterpart: they keep old call shapes working.
- Prefer documenting adapters next to intentional renames in release notes.

## Suggesting adapter drafts (#62)

Generate a **reviewable** draft from two snapshots. Suggestions are never
auto-applied by CI — humans must review and opt in before shipping.

```bash
tool-semantics capture examples/github_server_v1.json -o .tool-semantics/v1.json
tool-semantics capture examples/github_server_v2.json -o .tool-semantics/v2.json
tool-semantics suggest-adapter .tool-semantics/v1.json .tool-semantics/v2.json \
  -o .tool-semantics/adapter.suggested.json
```

```python
from tool_semantics.scanner import capture_manifest
from tool_semantics.suggest import suggest_adapter
from pathlib import Path

baseline = capture_manifest(Path("examples/github_server_v1.json"))
candidate = capture_manifest(Path("examples/github_server_v2.json"))
draft = suggest_adapter(baseline, candidate)
assert draft.auto_apply is False
print(draft.adapter.aliases, draft.notes)
```

### What gets suggested

| Signal | Action | Confidence |
| --- | --- | --- |
| `tool.renamed` in the report | `ToolAlias` | high |
| Remaining remove+add above suggestion threshold | `ToolAlias` | medium/low |
| Removed+added parameters with name similarity | `ArgumentMap.rename` | high/medium/low |
| Enums with equal cardinality + unique token matches | `EnumMap` | medium |
| Required parameter adds / tied enums / cardinality mismatch | skipped | skipped |

### Confidence limits

- Heuristic renames can be wrong when two unrelated tools look similar.
- Enum remaps are skipped when values cannot be paired unambiguously.
- New required parameters never get invented defaults.
- Treat every draft as a starting point for review, not production config.

## MCP compatibility proxy

`CompatibilityProxy` is an in-process shim. A network MCP proxy that speaks
stdio/SSE on both sides can wrap the same adapter object later; the translation
logic stays here.
