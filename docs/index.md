# Documentation index

Start here if you are new: [simple-explanation.md](simple-explanation.md) →
[concepts.md](concepts.md) → beginner path on the [README](../README.md).

## By topic

| Topic | Doc |
| --- | --- |
| Plain-language overview | [simple-explanation.md](simple-explanation.md) |
| Shared vocabulary | [concepts.md](concepts.md) |
| Architecture / pipeline | [architecture.md](architecture.md) |
| Snapshots & live MCP capture | [mcp-versions.md](mcp-versions.md), [adr-live-mcp-capture.md](adr-live-mcp-capture.md) |
| Structural diff & change codes | [change-codes.md](change-codes.md) |
| Semantics & agent risk | [concepts.md](concepts.md)#semantics-agent-behavior |
| Probes (offline / model) | [probes.md](probes.md) |
| Traces (roadmap) | [AGENT_EXECUTION.md](AGENT_EXECUTION.md), ROADMAP #83–#84 |
| Safety / risk field | [concepts.md](concepts.md)#safety, [probes.md](probes.md) |
| Policies & ignore config | [config.md](config.md) |
| Benchmarks / research | [AGENT_EXECUTION.md](AGENT_EXECUTION.md), [PLAN.md](PLAN.md) |
| GitHub Action (protect) | [github-action.md](github-action.md) |
| Migration adapters | [adapters.md](adapters.md) |
| Downstream consumers | [downstream.md](downstream.md) |
| Publishing | [publishing.md](publishing.md) |

## Beginner vs advanced CLI

**Beginner (capture → evaluate → protect)**

1. `capture` / `capture-mcp`
2. `compare` + `probe`
3. CI Action / non-zero exit

**Advanced / secondary**

- `--config` ignore rules, provenance sidecars, verbose stderr logs
- `--model` / `--trials` model-backed probes
- Library APIs for custom runners, adapters, policies

Unified `eval` ([#76](https://github.com/askmy-stack/tool-semantics/issues/76))
will become the single evaluate entrypoint; `compare` and `probe` remain for
advanced workflows.

## Milestone 7+ plan

- [PLAN.md](PLAN.md) — course of action  
- [AGENT_EXECUTION.md](AGENT_EXECUTION.md) — binding priority tables  
- [../ROADMAP.md](../ROADMAP.md) — checklist  
- [../CLAUDE.md](../CLAUDE.md) — short agent guidance
