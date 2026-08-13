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
- `src/tool_semantics/mcp_capture.py` — live MCP capture over stdio
- `src/tool_semantics/diff.py` — structural comparison engine
- `src/tool_semantics/models.py` — snapshot/report data models
- `src/tool_semantics/probes.py` — offline behavioral probe harness (`Probe`, `ProbeKind`, `evaluate_probes`)
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

1. **P0 — Ship a real release** ([#31](https://github.com/askmy-stack/tool-semantics/issues/31)): no GitHub Release or working `pip install tool-semantics` exists yet, despite the publish workflow being built. This blocks everything downstream.
2. **P1 — Provider-neutral model runner** ([#45](https://github.com/askmy-stack/tool-semantics/issues/45)): unblocks the model-backed probe work (#44, #46, #47) that closes the layers-3-5 gap.
3. **Ongoing**: dependency/CI hygiene is already automated via Dependabot — no action needed unless a PR fails.

Full phased plan, dependencies between issues, and required agent roles per
phase: [docs/PLAN.md](docs/PLAN.md).
