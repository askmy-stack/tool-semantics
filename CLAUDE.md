# CLAUDE.md

Guidance for Claude Code sessions working in this repo. Keep this file short;
the full roadmap and agent breakdown lives in [docs/PLAN.md](docs/PLAN.md).

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

Status: layers 1-2 are fully implemented and CI-gateable (structural diff,
exit codes 0/1/2). Layers 3-5 exist only as heuristic warnings today — closing
that gap is the main open work (see Current priorities below).

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

tool-semantics capture examples/github_server_v1.json -o .tool-semantics/v1.json
tool-semantics compare .tool-semantics/v1.json .tool-semantics/v2.json --markdown-output report.md
```

## Current priorities (condensed — see docs/PLAN.md for full sequencing)

1. **Ops — Cut `v0.3.0` GitHub Release + PyPI** so Action pins and
   `pip install tool-semantics==0.3.0` match `main` (see
   [docs/publishing.md](docs/publishing.md)). First release
   ([#31](https://github.com/askmy-stack/tool-semantics/issues/31)) already
   shipped as `v0.2.0`.
2. **Land remaining issue work** on `main`: remote SSE capture (#43), model
   runner (#45), model-backed probes (#44), metrics (#46), stability (#47).
3. **Downstream**: myelinmesh usage-weighted severity after #46 metrics are
   published; optional dogfood capture against market-pulse-mcp.
4. **Ongoing**: Dependabot hygiene — no action unless a PR fails.

Full phased plan: [docs/PLAN.md](docs/PLAN.md).
