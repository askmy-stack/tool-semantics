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
- [x] SSE / remote transport (`capture-mcp --sse`) — [#43](https://github.com/askmy-stack/tool-semantics/issues/43)

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
- [x] Human-reviewed probe generation / model-backed runners — [#44](https://github.com/askmy-stack/tool-semantics/issues/44)

## Milestone 4 — Model matrix
- [x] Provider-neutral runner — [#45](https://github.com/askmy-stack/tool-semantics/issues/45)
- [x] Tool-selection and argument-validity metrics — [#46](https://github.com/askmy-stack/tool-semantics/issues/46)
- [x] Repeated trials and stability scoring — [#47](https://github.com/askmy-stack/tool-semantics/issues/47)
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

## Milestone 7 — Modern MCP capture (DETECT)
- [x] Streamable HTTP remote capture — [#59](https://github.com/askmy-stack/tool-semantics/issues/59)
- [x] Multi-generation protocol negotiation / metadata — [#73](https://github.com/askmy-stack/tool-semantics/issues/73)
- [x] Bare-URL remote auto-detect (HTTP → SSE) — [#74](https://github.com/askmy-stack/tool-semantics/issues/74)
- [ ] Protocol / capability structural diffs — [#75](https://github.com/askmy-stack/tool-semantics/issues/75)

## Milestone 8 — Unified evaluation UX (TEST → PROTECT)
- [x] Probe CLI surface — [#57](https://github.com/askmy-stack/tool-semantics/issues/57) **P0** (this PR)
- [ ] Probe gates in CI Action — [#58](https://github.com/askmy-stack/tool-semantics/issues/58) **P0**
- [ ] Unified `eval` command — [#76](https://github.com/askmy-stack/tool-semantics/issues/76) **P0**
- [ ] Final-state verifier — [#105](https://github.com/askmy-stack/tool-semantics/issues/105) **P1**
- [ ] pass@k / pass^k reliability metrics — [#106](https://github.com/askmy-stack/tool-semantics/issues/106) **P1**
- [ ] Compatibility scorecard — [#77](https://github.com/askmy-stack/tool-semantics/issues/77) **P1**
- [ ] Eval-style PR comments — [#78](https://github.com/askmy-stack/tool-semantics/issues/78) **P1**
- [ ] `behavior.*` change codes (deferred) — [#61](https://github.com/askmy-stack/tool-semantics/issues/61) **P1**
- [ ] Stateful workflows — [#108](https://github.com/askmy-stack/tool-semantics/issues/108) **P1**
- [ ] No-tool correctness — [#107](https://github.com/askmy-stack/tool-semantics/issues/107) **P1**

## Milestone 9 — Semantic intelligence
- [ ] Tool collision / confusability — [#79](https://github.com/askmy-stack/tool-semantics/issues/79) **P1**
- [ ] Multi-signal rename confidence — [#80](https://github.com/askmy-stack/tool-semantics/issues/80) **P1**
- [ ] Optional embedding layer — [#117](https://github.com/askmy-stack/tool-semantics/issues/117) **P2**
- [ ] Optional LLM semantic judge — [#81](https://github.com/askmy-stack/tool-semantics/issues/81) **P2**
- [ ] Semantic distance / clustering — [#82](https://github.com/askmy-stack/tool-semantics/issues/82) **P2**

## Milestone 10 — Traces & workflows
- [ ] Trace schema + capture — [#83](https://github.com/askmy-stack/tool-semantics/issues/83) **P1**
- [ ] Trace replay — [#84](https://github.com/askmy-stack/tool-semantics/issues/84) **P1**
- [ ] Project layout / discovery baselines — [#85](https://github.com/askmy-stack/tool-semantics/issues/85), [#86](https://github.com/askmy-stack/tool-semantics/issues/86) **P2/P1**
- [ ] Cross-application workflows — [#112](https://github.com/askmy-stack/tool-semantics/issues/112) **P2**

## Milestone 11 — Safety, output, MCP-wide
- [ ] Safety scope / side effects / confirmation — [#87](https://github.com/askmy-stack/tool-semantics/issues/87) **P1**
- [ ] Expanded probe kinds — [#88](https://github.com/askmy-stack/tool-semantics/issues/88) **P2**
- [ ] Output-schema compatibility — [#89](https://github.com/askmy-stack/tool-semantics/issues/89) **P1**
- [ ] Prompt / resource / extension diffs — [#90](https://github.com/askmy-stack/tool-semantics/issues/90), [#91](https://github.com/askmy-stack/tool-semantics/issues/91) **P1/P2**
- [ ] Integrity monitoring — [#113](https://github.com/askmy-stack/tool-semantics/issues/113) **P2**
- [ ] Efficiency regression — [#114](https://github.com/askmy-stack/tool-semantics/issues/114) **P2**

## Milestone 12+ — Prove (benchmarks, research, DX)
- [ ] Difficulty / messiness + horizon — [#109](https://github.com/askmy-stack/tool-semantics/issues/109), [#110](https://github.com/askmy-stack/tool-semantics/issues/110) **P2**
- [ ] Format-sensitivity fuzz — [#111](https://github.com/askmy-stack/tool-semantics/issues/111) **P2**
- [ ] Corpus / mutations / research harness — [#92](https://github.com/askmy-stack/tool-semantics/issues/92)–[#95](https://github.com/askmy-stack/tool-semantics/issues/95) **P2/P3**
- [ ] Confidence intervals + dev/test/verified split — [#115](https://github.com/askmy-stack/tool-semantics/issues/115), [#116](https://github.com/askmy-stack/tool-semantics/issues/116) **P3**
- [ ] DX: init/doctor/lint/audit/generate-probes — [#96](https://github.com/askmy-stack/tool-semantics/issues/96)–[#98](https://github.com/askmy-stack/tool-semantics/issues/98) **P2**
- [x] Docs / README capture+eval positioning — [#101](https://github.com/askmy-stack/tool-semantics/issues/101) **P2**
- [x] ROADMAP/PLAN + agent execution spec — [#103](https://github.com/askmy-stack/tool-semantics/issues/103)
- [ ] Apply GitHub priority labels — [#118](https://github.com/askmy-stack/tool-semantics/issues/118) **P0**
- Operational spec: [docs/AGENT_EXECUTION.md](docs/AGENT_EXECUTION.md)
