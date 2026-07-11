# Roadmap

## Milestone 0 — Foundation
- [x] Python package and CLI (`tool-semantics`)
- [x] Snapshot model
- [x] JSON manifest scanner
- [x] Structural comparison engine
- [x] Markdown + JSON reports
- [x] Tests and CI
- [x] Publish repository

## Milestone 1 — Live MCP capture
- [x] Connect to local MCP servers over stdio (`capture-mcp`) — [#11](https://github.com/askmy-stack/tool-semantics/issues/11)
- [x] Discover tools, prompts, and resources
- [x] Normalize metadata into a stable snapshot
- [x] Redact secrets and unstable fields
- [ ] SSE / remote transport (stubbed with clear error)

## Milestone 2 — Compatibility engine
- [x] Required-parameter, type, and enum changes
- [x] Description-change warnings
- [x] Risk-level escalation detection
- [x] JSON and Markdown reports
- [x] CI-compatible exit codes
- [x] Default-value and `output_schema` change codes — [#8](https://github.com/askmy-stack/tool-semantics/issues/8), [#15](https://github.com/askmy-stack/tool-semantics/issues/15)
- [x] Snapshot version validation on read — [#7](https://github.com/askmy-stack/tool-semantics/issues/7)
- [x] Ignore-config + verbose logging for CI adoption — [#9](https://github.com/askmy-stack/tool-semantics/issues/9), [#10](https://github.com/askmy-stack/tool-semantics/issues/10)
- [x] Type narrowing / widening codes — [#25](https://github.com/askmy-stack/tool-semantics/issues/25)
- [x] Heuristic tool rename detection — [#24](https://github.com/askmy-stack/tool-semantics/issues/24)

## Milestone 3 — Behavioral contracts
- [x] Offline probe harness (positive / negative / ambiguous) — [#12](https://github.com/askmy-stack/tool-semantics/issues/12)
- [x] Side-effect and confirmation expectations (`max_risk`, `requires_confirmation`)
- [ ] Human-reviewed probe generation / model-backed runners

## Milestone 4 — Model matrix
- [ ] Provider-neutral runner
- [ ] Tool-selection and argument-validity metrics
- [ ] Repeated trials and stability scoring
- [x] Large-manifest benchmarks (library helper + test gate) — [#14](https://github.com/askmy-stack/tool-semantics/issues/14)

## Milestone 5 — Pull-request reporting
- [x] Baseline versus candidate comparison (CLI)
- [x] PR comments via composite GitHub Action — [#13](https://github.com/askmy-stack/tool-semantics/issues/13)
- [x] Release-policy enforcement knobs (`--policy` / `[policy]` / Action `policy`)
- [x] PyPI publish / trusted publishing workflow — [#23](https://github.com/askmy-stack/tool-semantics/issues/23)

## Milestone 6 — Migration adapters
- [x] Tool aliases / rename detection (heuristic warning)
- [x] Argument and enum translation (`MigrationAdapter`)
- [x] Output wrappers
- [x] In-process MCP compatibility proxy (`CompatibilityProxy`)
