# MCP extensions (#91)

Capture and diff **extensions** / experimental capabilities advertised at MCP
`initialize`. Support is **best-effort** across protocol generations — unknown
shapes are ignored rather than invented.

## Snapshot field

Live captures store a normalized map under:

```json
{
  "metadata": {
    "extensions": {
      "io.modelcontextprotocol/sampling": {
        "name": "io.modelcontextprotocol/sampling",
        "version": "1.0.0",
        "source": "capabilities.extensions",
        "details": {}
      }
    }
  }
}
```

### Sources (in order of ingest)

| Source | Notes |
| --- | --- |
| `initialize.extensions` | Top-level object or list when present |
| `capabilities.extensions` | Nested under server capabilities |
| `capabilities.experimental` | Treated as experimental extension stubs |

Manifest-only snapshots typically omit `extensions`; compare skips the layer
when **both** sides lack it (no false noise).

## Diff codes

| Code | Severity | Meaning |
| --- | --- | --- |
| `extension.removed` | breaking | Extension present in baseline, absent in candidate |
| `extension.added` | info | New extension advertised |
| `extension.version_changed` | breaking / warning | Version string changed (breaking when both sides pinned) |

## Partial / unknown support

- Older protocol generations may not advertise extensions at all — absence is
  not treated as “empty set” unless the other side has extensions.
- Unrecognized value shapes are stored with best-effort `details` rather than
  failing capture.
- Clients should not assume every MCP server implements the same extension
  vocabulary.

## Library

```python
from tool_semantics.extensions import extract_extensions_from_initialize
from tool_semantics.diff import compare_snapshots

exts = extract_extensions_from_initialize(initialize_result)
report = compare_snapshots(baseline_snap, candidate_snap)
```

## Task-capability stub (follow-on)

Long-running MCP **tasks** (start / status / complete / cancel) are **out of
scope** for this PR. See [adr-mcp-tasks.md](adr-mcp-tasks.md) for the stub ADR.
