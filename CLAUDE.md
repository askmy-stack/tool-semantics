# CLAUDE.md

Guidance for Claude Code sessions working in this repo. Keep this file short;
the full roadmap and agent breakdown lives in [docs/PLAN.md](docs/PLAN.md) and
[docs/AGENT_EXECUTION.md](docs/AGENT_EXECUTION.md).

## What this repo is

**Tool-Semantics — Behavioral regression testing for MCP and AI-agent interfaces.**

Know when an MCP change breaks the agent, not just the schema.
**Schema-valid ≠ agent-safe.**

Product framing: **DETECT** (capture/compare) → **TEST** (probes) → **PROTECT** (CI).
Beginner path: capture → compare + probe (unified `eval` is #76).
Docs: [docs/simple-explanation.md](docs/simple-explanation.md),
[docs/index.md](docs/index.md).

It snapshots a tool interface, diffs baseline vs. candidate, and reports risk
across five compatibility layers:

1. Protocol — can the client still speak to the server?
2. Schema — are parameters/types still valid?
3. Tool selection — will models still pick the right tool?
4. Execution — do calls still succeed with prior argument patterns?
5. Intent / side effects — did risk or confirmation needs change?

Status: layers 1–2 are CI-gateable; layers 3–5 are covered by offline probes
plus **opt-in** model-backed probes (library). Live capture supports stdio,
Streamable HTTP, and legacy SSE.

## Repo layout

- `src/tool_semantics/scanner.py` — captures manifests into `InterfaceSnapshot`
- `src/tool_semantics/mcp_capture.py` — live MCP capture (stdio / HTTP / SSE)
- `src/tool_semantics/diff.py` — structural comparison engine
- `src/tool_semantics/models.py` — snapshot/report data models
- `src/tool_semantics/probes.py` — offline + opt-in model-backed probe harness
- `src/tool_semantics/runner.py` — provider-neutral model runner interface
- `src/tool_semantics/adapters.py` — migration adapters (tool alias/arg translation)
- `src/tool_semantics/policy.py` — release-policy enforcement knobs
- `src/tool_semantics/redact.py` — secret/unstable-field redaction
- `src/tool_semantics/report.py` — Markdown/JSON report rendering
- `src/tool_semantics/cli.py` — Typer CLI entrypoint
- `tests/` — pytest suite, one file per module area
- `examples/` — demo MCP-style manifests (GitHub server v1/v2, weather)
- `docs/` — [index](docs/index.md), simple-explanation, concepts, architecture,
  config, change-codes, probes, github-action, publishing, adapters

## Dev commands

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

pytest
ruff check .
ruff format --check .

tool-semantics capture examples/github_server_v1.json -o .tool-semantics/v1.json
tool-semantics compare .tool-semantics/v1.json .tool-semantics/v2.json --markdown-output report.md
tool-semantics probe .tool-semantics/v2.json --probes examples/probes/github_v1_offline.json
tool-semantics capture-mcp -o snap.json https://example.com/mcp
```

## Current priorities

1. **P0** — Probe CLI (#57) → CI probe gates (#58) → unified `eval` (#76).
2. **P1** — Final-state / reliability / protocol diffs (#105, #106, #75) and scorecard (#77).
3. Maintainer: apply GitHub priority labels (#118) — agents cannot label via API.
4. Full prioritized backlog: [docs/AGENT_EXECUTION.md](docs/AGENT_EXECUTION.md).

Full plan: [docs/PLAN.md](docs/PLAN.md).
