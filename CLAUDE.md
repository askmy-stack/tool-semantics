# CLAUDE.md

Guidance for Claude Code sessions working in this repo. Keep this file short;
the full post-Milestone-4 course of action lives in [docs/PLAN.md](docs/PLAN.md).

## What this repo is

**tool-semantics** is a Python CLI/library that catches breaking changes in
AI-agent tool interfaces (MCP servers, tool APIs) before they ship. It
snapshots a tool interface, diffs baseline vs. candidate, and reports risk
across five compatibility layers:

1. Protocol — can the client still speak to the server?
2. Schema — are parameters/types still valid?
3. Tool selection — will models still pick the right tool?
4. Execution — do calls still succeed with prior argument patterns?
5. Intent / side effects — did risk or confirmation needs change?

Status: layers 1–2 are CI-gateable; layers 3–5 are covered by offline probes
plus **opt-in** model-backed probes, metrics, and stability scoring (Milestones
3–4). Live capture supports stdio and SSE.

## Repo layout

- `src/tool_semantics/scanner.py` — captures manifests into `InterfaceSnapshot`
- `src/tool_semantics/mcp_capture.py` — live MCP capture over stdio and SSE
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
```

## Current priorities

1. **Downstream** — myelinmesh usage-weighted severity from probe metrics
   ([docs/downstream.md](docs/downstream.md), myelinmesh#21).
2. **Hygiene** — keep CI green (`ruff format`, tests); Dependabot only when PRs fail.
3. **Releases** — tag from `main` per [docs/publishing.md](docs/publishing.md).

Full plan: [docs/PLAN.md](docs/PLAN.md).
