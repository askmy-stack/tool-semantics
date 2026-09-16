# Course of action (Milestones 7+)

Primary operational spec: [AGENT_EXECUTION.md](AGENT_EXECUTION.md).  
Product positioning: behavioral regression for MCP / AI-agent interfaces.

Shipped through **v0.4.0**: Milestones 0–6 (structural detect, stdio/SSE capture,
offline + library model probes, policy, Action, adapters).

## Phase order

1. **Modernize** — Streamable HTTP, protocol negotiation, bare-URL capture (#59, #73, #74)
2. **Simplify** — `eval` as primary UX (#57, #58, #76, #77, #78, #61)
3. **Evaluate real behavior** — collision/rename, traces, discovery, safety/output (#79–#91)
4. **Prove** — corpus, mutations, research harness, DX/docs (#92–#103)

## Immediate next PRs

| Order | Issues | Outcome |
| --- | --- | --- |
| 1 | #75 | Protocol/capability diffs |
| 2 | #57 #58 | Probe CLI + CI gates |
| 3 | #76 | Unified `eval` |
| 4 | #61 #77 #78 | Behavior codes + scorecard + PR comments |

Shipped: Streamable HTTP + protocol negotiation + bare-URL auto-detect (#59, #73, #74).

## Non-goals

Dashboards, SaaS, generic agent runtimes — see AGENT_EXECUTION.md.
