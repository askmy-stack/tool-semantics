# CLAUDE.md

Guidance for Claude Code sessions working in this repo. Keep this file short;
the full roadmap and agent breakdown lives in [docs/PLAN.md](docs/PLAN.md) and
[docs/AGENT_EXECUTION.md](docs/AGENT_EXECUTION.md).

## What this repo is

**Tool-Semantics — Behavioral regression testing for MCP and AI-agent interfaces.**

Know when an MCP change breaks the agent, not just the schema.

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
- `docs/` — architecture, config, change-codes, github-action, publishing, adapters

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
tool-semantics capture-mcp -o snap.json https://example.com/mcp
```

## Current priorities

1. **P0 remaining** — protocol/capability diffs (#75), then unified `eval` (#57/#58/#76).
2. **Downstream** — myelinmesh usage-weighted severity ([docs/downstream.md](docs/downstream.md)).
3. **Hygiene** — keep CI green; Dependabot only when PRs fail.

Full plan: [docs/PLAN.md](docs/PLAN.md). Execution rules: [docs/AGENT_EXECUTION.md](docs/AGENT_EXECUTION.md).
