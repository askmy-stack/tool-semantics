# Unified eval

`tool-semantics eval` is the **primary product command**: one invocation runs
structural compare, optional semantic / safety sectioning, probes, stability,
and release policy → a single Markdown/JSON report.

Advanced commands (`compare`, `probe`, `capture`, `capture-mcp`) remain
available for focused workflows.

## Pipeline

```text
load snapshots
  → structural diff (+ ignore rules)
  → partition Semantic / Safety change codes
  → optional probes (offline or model) + stability trials
  → release policy
  → unified report + FINAL RESULT
```

Exit codes match `compare`: `0` pass, `1` policy / probe fail, `2` input error.

## CLI

```bash
tool-semantics capture examples/github_server_v1.json -o .tool-semantics/v1.json
tool-semantics capture examples/github_server_v2.json -o .tool-semantics/v2.json

tool-semantics eval \
  --baseline .tool-semantics/v1.json \
  --candidate .tool-semantics/v2.json \
  --probes examples/probes/github_v1_offline.json \
  --policy compatible \
  --markdown-output eval.md \
  --json-output eval.json
```

Flags mirror compare probe gates (`--probe-mode`, `--probe-trials`, …) and
config `[probes]` / `[policy]` — see [config.md](config.md) and
[probes.md](probes.md).

## Report sections

| Section | Source |
| --- | --- |
| Structural | Schema / tool / parameter codes (removals, required params, types, …) |
| Semantic | Soft selection signals (`tool.description_changed`, `tool.renamed`, …) |
| Safety | `tool.risk_changed` (and future safety scope codes) |
| Behavioral | Probe gate results / metrics when `--probes` or `[probes]` is set |
| Stability | Present when model-backed `--probe-trials` > 1 |
| FINAL RESULT | Combined structural policy + probe thresholds |

Behavioral failures are **metrics / gate breaches** today; folding them into
`behavior.*` change codes is tracked in [#61](https://github.com/askmy-stack/tool-semantics/issues/61).
