# Course of action (Milestones 7+)

Primary operational spec: [AGENT_EXECUTION.md](AGENT_EXECUTION.md).  
Product positioning: **schema-valid ≠ agent-safe** — behavioral regression for
MCP / AI-agent interfaces ([simple-explanation.md](simple-explanation.md),
[concepts.md](concepts.md), [index.md](index.md)).

Shipped through **v0.4.0**: Milestones 0–6 (structural detect, stdio/SSE capture,
offline + library model probes, policy, Action, adapters).

## Phase order

1. **Modernize** — Streamable HTTP, protocol negotiation, bare-URL capture (#59, #73, #74)
2. **Simplify** — `eval` as primary UX (#57, #58, #76, #77, #78, #61)
3. **Evaluate real behavior** — collision/rename, traces, discovery, safety/output (#79–#91)
4. **Prove** — corpus, mutations, research harness, DX/docs (#92–#103)

Beginner UX today: **capture → compare + probe**. Unified `eval` (#76) becomes
the single evaluate entrypoint when merged.

## Immediate next PRs

| Order | Issues | Priority | Outcome |
| --- | --- | --- | --- |
| 1 | #75 | P1 | Protocol/capability diffs |
| 2 | #57 #58 | P0 | Probe CLI + CI gates |
| 3 | #76 | P0 | Unified `eval` |
| 4 | #105 #106 | P1 | Final-state + pass@k/pass^k |
| 5 | #61 #77 #78 | P1 | Behavior codes + scorecard + PR comments |

Shipped (PR #104): Streamable HTTP + protocol negotiation + bare-URL (#59, #73, #74).  
New execution-spec gaps filed: #105–#117. Maintainer labeling: #118.

Full priority tables: [AGENT_EXECUTION.md](AGENT_EXECUTION.md).

## Non-goals

Dashboards, SaaS, generic agent runtimes — see AGENT_EXECUTION.md.
