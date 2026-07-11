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
- Connect to local and remote MCP servers
- Discover tools, prompts, and resources
- Normalize metadata into a stable snapshot
- Redact secrets and unstable fields

## Milestone 2 — Compatibility engine
- Required-parameter, type, enum, default, and output changes
- Description-change warnings
- Risk-level escalation detection
- JSON and Markdown reports
- CI-compatible exit codes

## Milestone 3 — Behavioral contracts
- Positive, negative, and ambiguous intents
- Side-effect and confirmation expectations
- Human-reviewed probe generation

## Milestone 4 — Model matrix
- Provider-neutral runner
- Tool-selection and argument-validity metrics
- Repeated trials and stability scoring

## Milestone 5 — Pull-request reporting
- Baseline versus candidate comparison
- PR comments and detailed artifacts
- Release-policy enforcement

## Milestone 6 — Migration adapters
- Tool aliases
- Argument and enum translation
- Output wrappers
- MCP compatibility proxy
