# Agent execution specification (operational)

This is the **operational** guide for agents working in this repository.
It summarizes the full vision (“behavioral regression for MCP / AI-agent
interfaces”) against the **current codebase** and the **issue backlog**.

Positioning (use consistently):

> **Tool-Semantics — Behavioral regression testing for MCP and AI-agent interfaces.**  
> Know when an MCP change breaks the agent, not just the schema.

## Baseline (verified)

- Full test suite: **passing** (`pytest`, `ruff check`).
- Package version on `main`: **0.4.0**.
- Layers: **DETECT** (structural diff) shipped; **TEST** (probes/runner) library-only;
  **PROTECT** (policy/Action) structural-only.

## Completed vs missing (gap analysis)

### Completed (do not reimplement)

| Area | Location |
| --- | --- |
| Manifest capture / snapshots | `scanner.py`, `models.py` |
| Structural diff + change codes | `diff.py`, `docs/change-codes.md` |
| Risk levels, output_schema, rename heuristic | `diff.py`, `models.py` |
| MCP stdio + legacy SSE capture | `mcp_capture.py` |
| Offline + model-backed probes, metrics, trials | `probes.py`, `runner.py` |
| Policy, ignore config, adapters/proxy | `policy.py`, `config.py`, `adapters.py` |
| Reports + CI Action | `report.py`, `.github/actions/compare` |
| Large-manifest timing helper | `benchmarks.py` |

### Partial

| Capability | Gap | Issues |
| --- | --- | --- |
| Remote MCP | Streamable HTTP + SSE + bare-URL auto-detect | Done (#59, #74); capability diffs still open (#75) |
| Protocol versions | Negotiated + recorded in metadata | Done (#73); see `docs/mcp-versions.md` |
| Protocol/capability diff | Not compared | #75 |
| Probes in CLI/CI | Library only | #57, #58 |
| Unified `eval` | Missing | #76 |
| `behavior.*` codes | Deferred | #61 |
| Semantic collision / rename confidence | Token Jaccard rename only | #79, #80 |
| Trace replay | Missing | #83, #84 |
| Safety scope/side-effects | Single `RiskLevel` | #87 |
| Prompt/resource structural codes | Captured, thinly compared | #90 |

### Missing (high level)

Final-state verifier, pass@k/pass^k as first-class CLI metrics, messiness/horizon,
no-tool probes, format fuzz, integrity monitor, efficiency regression, verified
benchmark corpus, mutation generator, `init`/`doctor`/`lint`/`audit`, demo MCP
variants — see issues **#76–#103**.

### Architectural conflicts / constraints

- Extend modules listed in `CLAUDE.md`; do not rewrite the package.
- Deterministic paths must work **without** model SDKs.
- Never auto-execute discovered tools; never persist auth secrets in snapshots.
- Do not silently change severities; document report/schema changes.
- Prefer DETERMINISTIC findings; label MODEL-BASED explicitly.

## Non-goals (until engine is mature)

SaaS, auth/billing, large dashboards, generic agent frameworks, unrelated RAG/chat.

## Execution order (binding)

```text
MODERNIZE → SIMPLIFY → EVALUATE REAL BEHAVIOR → PROVE RESULTS
```

1. **P0** Protocol/capability diffs: #75
2. **P0** Unified eval path: #57 → #58 → #76 (+ #61, #77, #78)
3. **P1** Semantic + traces: #79/#80 → #83/#84 → #86
4. **P2** Safety/output/MCP-wide: #87–#91
5. **P3** Benchmarks/research/UX: #92–#103

Shipped in this modernization wave: Streamable HTTP (#59), protocol negotiation
(#73), bare-URL auto-detect (#74).

## Definition of done (every milestone)

Implementation + tests + docs + failure modes + reporting hooks + backward
compatibility check + examples when useful.

## Progress report template

After each milestone PR: what shipped, files, tests, compatibility impact,
limitations, next step.
