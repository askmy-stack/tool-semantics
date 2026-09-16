# Tool-Semantics in plain language

**Schema-valid is not the same as agent-safe.**

Typed clients fail loudly when a field disappears. Language-model agents often
**guess**: they pick tools from descriptions, invent arguments from schemas, and
infer side effects from names. A change that still validates as JSON Schema can
still break the agent.

Tool-Semantics answers one question:

> If we ship this MCP / tool-interface change, will agents still behave?

## Three jobs: DETECT · TEST · PROTECT

| Job | What you do | Typical command |
| --- | --- | --- |
| **DETECT** | Snapshot the interface; see what changed | `capture`, `capture-mcp`, `compare` |
| **TEST** | Check whether agents still pick tools / args correctly | `probe` (offline or `--model`) |
| **PROTECT** | Gate merges in CI with policies and reports | GitHub Action, exit codes, config |

## Beginner path

1. **Capture** a baseline and a candidate snapshot.
2. **Evaluate** with structural compare plus behavioral probes.
3. **Protect** the merge when the report fails policy.

```bash
# 1. Capture
tool-semantics capture examples/github_server_v1.json -o .tool-semantics/v1.json
tool-semantics capture examples/github_server_v2.json -o .tool-semantics/v2.json

# 2. Evaluate (structural + behavioral)
tool-semantics compare .tool-semantics/v1.json .tool-semantics/v2.json \
  --markdown-output .tool-semantics/report.md
tool-semantics probe .tool-semantics/v2.json \
  --probes examples/probes/github_v1_offline.json

# 3. Protect — non-zero exit fails CI (see docs/github-action.md)
```

A unified `eval` command ([#76](https://github.com/askmy-stack/tool-semantics/issues/76))
will combine compare + probes into one beginner entrypoint; until then, use the
two commands above.

## What “breaking” means here

- **Breaking / critical** structural codes fail `compare` by default
  ([change-codes.md](change-codes.md)).
- **Warnings** (e.g. description drift) flag selection risk without always
  failing CI — agents may re-route even when schemas remain valid.
- **Probes** catch behavioral regressions that pure schema diffs miss.

Next: [concepts.md](concepts.md) · [index.md](index.md) · [README](../README.md)
