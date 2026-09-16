# Agent execution specification (operational)

This is the **operational** guide for agents working in this repository.
It summarizes the full vision (“behavioral regression for MCP / AI-agent
interfaces”) against the **current codebase** and the **issue backlog**.

Positioning (use consistently):

> **Tool-Semantics — Behavioral regression testing for MCP and AI-agent interfaces.**  
> Know when an MCP change breaks the agent, not just the schema.

## Baseline (verified)

- Full test suite: **passing** (`pytest`, `ruff check`).
- Package version on `main`: **0.4.0** (PR #104 adds Streamable HTTP on branch).
- Layers: **DETECT** (structural diff) shipped; **TEST** (probes/runner) library-only;
  **PROTECT** (policy/Action) structural-only.

## Completed vs missing (gap analysis)

### Completed (do not reimplement)

| Area | Location |
| --- | --- |
| Manifest capture / snapshots | `scanner.py`, `models.py` |
| Structural diff + change codes | `diff.py`, `docs/change-codes.md` |
| Risk levels, output_schema, rename heuristic | `diff.py`, `models.py` |
| MCP stdio + SSE + Streamable HTTP + bare URL | `mcp_capture.py` (#59/#73/#74 via PR #104) |
| Offline + model-backed probes, metrics, trials | `probes.py`, `runner.py` |
| Policy, ignore config, adapters/proxy | `policy.py`, `config.py`, `adapters.py` |
| Reports + CI Action | `report.py`, `.github/actions/compare` |
| Large-manifest timing helper | `benchmarks.py` |

### Partial / open

| Capability | Gap | Issues | Priority |
| --- | --- | --- | --- |
| Protocol/capability diff | Not compared | #75 | P1 |
| Probes in CLI/CI | Library only | #57, #58 | P0 |
| Unified `eval` | Missing | #76 | P0 |
| Final-state verifier | Probe `expected_state` + axes | #105 | P1 |
| pass@k / pass^k | Library trials only | #106 | P1 |
| `behavior.*` codes | Deferred | #61 | P1 |
| Semantic collision / rename / embeddings | Token Jaccard only | #79, #80, #117 | P1/P2 |
| No-tool / workflows | Missing | #107, #108 | P1 |
| Trace replay | Missing | #83, #84 | P1 |
| Safety scope/side-effects | Single `RiskLevel` | #87 | P1 |
| Prompt/resource codes | Thin compare | #90 | P1 |

## Prioritized backlog

> **Note:** Agents cannot apply GitHub labels (`addLabelsToLabelable` 403). Priorities
> live here and in `[Pn]` title prefixes on new issues. Maintainers: apply labels per
> [#118](https://github.com/askmy-stack/tool-semantics/issues/118).

### P0 — Do now

| Issue | Title |
| --- | --- |
| #57 | Probe CLI (offline + model-backed) |
| #58 | Gate compare / Action on probe metrics |
| #59 | Streamable HTTP capture (PR #104) |
| #73 | Protocol negotiation (PR #104) |
| #74 | Bare-URL auto-detect (PR #104) |
| #76 | Unified `eval` command |
| #118 | Apply priority/area labels (maintainer) |

### P1 — Next product

| Issue | Title |
| --- | --- |
| #61 | `behavior.*` change codes |
| #75 | Protocol / capability / transport diffs |
| #77 | Compatibility scorecard + explanations |
| #78 | Eval-style GitHub Action PR comments |
| #79 | Tool collision / confusability |
| #80 | Multi-signal rename confidence |
| #83 | Versioned agent trace schema |
| #84 | Trace replay (single + batch) |
| #86 | Progressive discovery regression |
| #87 | Safety scope / side effects / confirmation |
| #89 | Field-level output-schema diffs |
| #90 | Prompt / resource structural diffs |
| #105 | Final-state verification |
| #106 | pass@k / pass^k reliability metrics |
| #107 | No-tool correctness probes |
| #108 | Stateful multi-step workflow evaluation |

### P2 — Follow-on

| Issue | Title |
| --- | --- |
| #62 | Adapter suggestions from diffs |
| #66 | Harden model prompts vs untrusted metadata |
| #70 | Example probe fixtures + README walkthrough |
| #81 | Optional LLM semantic judge |
| #82 | Semantic distance matrix / clustering |
| #85 | `.tool-semantics/` project layout |
| #88 | Expanded probe kinds (safety/routing/adversarial) |
| #91–#94 | Extensions, corpus, mutations, multi-model matrix |
| #96–#98 | `init`/`doctor`, `lint`/`audit`, probe generation |
| #101–#102 | Docs restructure, demo MCP variants |
| #109 | Difficulty / messiness metadata |
| #110 | Behavioral Compatibility Horizon |
| #111 | Format-sensitivity fuzz testing |
| #112 | Cross-application workflows |
| #113 | Integrity monitoring |
| #114 | Efficiency regression metrics |
| #117 | Optional embedding similarity layer |

### P3 — Polish / research

| Issue | Title |
| --- | --- |
| #60 | Extra provider adapters / packaging |
| #63–#65 | Snapshot registry design, coverage, dogfood |
| #67 #71 | myelinmesh tracking, floating `@v0` Action tag |
| #95 #99 #100 | Research harness, SARIF/HTML, parallel/cache |
| #115 | Confidence intervals for metrics |
| #116 | Dev / test / verified benchmark split |

## Architectural constraints

- Extend modules listed in `CLAUDE.md`; do not rewrite the package.
- Deterministic paths must work **without** model SDKs.
- Never auto-execute discovered tools; never persist auth secrets in snapshots.
- Do not silently change severities; document report/schema changes.
- Prefer DETERMINISTIC findings; label MODEL-BASED explicitly.
- Remote capture errors use prefixes: `[authentication]`, `[network]`,
  `[protocol]`, `[unsupported]`, `[invalid_response]`, `[timeout]`,
  `[unsupported_server]` (see `docs/mcp-versions.md`).

## Non-goals (until engine is mature)

SaaS, auth/billing, large dashboards, generic agent frameworks, unrelated RAG/chat.

## Execution order (binding)

```text
MODERNIZE → SIMPLIFY → EVALUATE REAL BEHAVIOR → PROVE RESULTS
```

1. **P0** Finish M7 merge (#59/#73/#74) → label backlog (#118) → #57 → #58 → #76
2. **P1** #75, #105, #106, #61, #77/#78, then semantic/traces/safety (#79–#90, #107–#108)
3. **P2** Embeddings/horizon/integrity/efficiency/DX (#109–#114, #117, #96–#98)
4. **P3** Research polish (#115–#116, #95, #99–#100)

## Definition of done (every milestone)

Implementation + tests + docs + failure modes + reporting hooks + backward
compatibility check + examples when useful.

## Progress report template

After each milestone PR: what shipped, files, tests, compatibility impact,
limitations, next step.
