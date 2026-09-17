# Demo MCP variants (#102)

Tiny **stdio** MCP server with four interface variants for local tutorials and
CI smoke tests. No network dependencies.

## Variants

| Variant | Intent | Expected compare vs `v1` |
| --- | --- | --- |
| `v1` | Baseline | — |
| `v2-safe` | Additive (optional param + new tool) | Compatible / info–warning only |
| `v2-breaking` | Remove `search_notes` + required `folder` | Breaking |
| `v2-confusing` | Near-duplicate `find_notes` | Info adds; selection collisions |

## Walkthrough

```bash
# Capture each variant
for v in v1 v2-safe v2-breaking v2-confusing; do
  tool-semantics capture-mcp -o ".tool-semantics/demo-$v.json" -- \
    python examples/demo-mcp/server.py "$v"
done

# Safe candidate — should stay policy-compatible under default breaking gate
tool-semantics compare \
  .tool-semantics/demo-v1.json .tool-semantics/demo-v2-safe.json \
  --markdown-output .tool-semantics/demo-safe.md

# Breaking candidate — expect tool.removed / parameter.added_required
tool-semantics compare \
  .tool-semantics/demo-v1.json .tool-semantics/demo-v2-breaking.json \
  --markdown-output .tool-semantics/demo-breaking.md

# Confusing candidate — new overlapping tool for selection risk demos
tool-semantics compare \
  .tool-semantics/demo-v1.json .tool-semantics/demo-v2-confusing.json \
  --markdown-output .tool-semantics/demo-confusing.md
```

Scorecard / eval PRs can plug these snapshots into behavioral reports; structural
diffs alone already show the intended contrast.

## Run the server alone

```bash
DEMO_MCP_VARIANT=v2-breaking python examples/demo-mcp/server.py
# or: python examples/demo-mcp/server.py v2-confusing
```
