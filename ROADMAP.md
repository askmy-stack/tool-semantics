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
- [ ] Connect to local and remote MCP servers (`capture --mcp`) — [#11](https://github.com/askmy-stack/tool-semantics/issues/11)
- [ ] Discover tools, prompts, and resources
- [ ] Normalize metadata into a stable snapshot
- [ ] Redact secrets and unstable fields

## Milestone 2 — Compatibility engine
- [x] Required-parameter, type, and enum changes
- [x] Description-change warnings
- [x] Risk-level escalation detection
- [x] JSON and Markdown reports
- [x] CI-compatible exit codes
- [ ] Default-value and `output_schema` change codes — [#8](https://github.com/askmy-stack/tool-semantics/issues/8), [#15](https://github.com/askmy-stack/tool-semantics/issues/15)
- [ ] Snapshot version validation on read — [#7](https://github.com/askmy-stack/tool-semantics/issues/7)
- [ ] Ignore-config + verbose logging for CI adoption — [#9](https://github.com/askmy-stack/tool-semantics/issues/9), [#10](https://github.com/askmy-stack/tool-semantics/issues/10)

## Milestone 3 — Behavioral contracts
- [ ] Positive, negative, and ambiguous intents — [#12](https://github.com/askmy-stack/tool-semantics/issues/12)
- [ ] Side-effect and confirmation expectations
- [ ] Human-reviewed probe generation

## Milestone 4 — Model matrix
- [ ] Provider-neutral runner
- [ ] Tool-selection and argument-validity metrics
- [ ] Repeated trials and stability scoring
- [ ] Large-manifest benchmarks — [#14](https://github.com/askmy-stack/tool-semantics/issues/14)

## Milestone 5 — Pull-request reporting
- [ ] Baseline versus candidate comparison
- [ ] PR comments and detailed artifacts — [#13](https://github.com/askmy-stack/tool-semantics/issues/13)
- [ ] Release-policy enforcement
- [ ] PyPI publish / trusted publishing workflow

## Milestone 6 — Migration adapters
- [ ] Tool aliases / rename detection
- [ ] Argument and enum translation
- [ ] Output wrappers
- [ ] MCP compatibility proxy
