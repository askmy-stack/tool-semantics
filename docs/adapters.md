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

## MCP compatibility proxy

`CompatibilityProxy` is an in-process shim. A network MCP proxy that speaks
stdio/SSE on both sides can wrap the same adapter object later; the translation
logic stays here.
