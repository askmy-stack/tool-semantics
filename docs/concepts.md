# Concepts and shared vocabulary

Short definitions used across Tool-Semantics docs and reports.

## Snapshots

A normalized **InterfaceSnapshot** of an MCP / tool catalog: tool names,
descriptions, parameters, optional output schemas, optional `risk`, plus
protocol/server metadata. Snapshots are the **canonical compare input** —
not live traffic.

- Capture from a JSON manifest: `capture`
- Capture from a live server: `capture-mcp` (stdio / Streamable HTTP / SSE)

See [architecture.md](architecture.md), [mcp-versions.md](mcp-versions.md).

## Diff / change codes

Deterministic comparison of baseline vs candidate snapshots. Each finding has a
stable **code** (e.g. `tool.removed`), **severity** (`info` → `critical`),
subject, and message.

Catalog: [change-codes.md](change-codes.md).  
Semantics note: description / rename warnings matter because models route on
prose, not only types.

## Semantics (agent behavior)

Beyond schema validity:

| Idea | Meaning |
| --- | --- |
| Tool selection | Will the model still pick the intended tool? |
| Argument patterns | Will prior argument shapes still validate? |
| Risk / confirmation | Did side-effect expectations change? |

## Probes

Behavioral checks against a snapshot.

- **Offline** — no LLM; assert expected tools / params / risk exist.
- **Model-backed** — opt-in runner selects a tool for an intent (`approved`
  probes by default).

See [probes.md](probes.md).

## Traces

Recorded agent trajectories (tool calls over time) for replay and regression.
Trace schema / replay land in Milestone work (#83–#84); not required for the
beginner capture → evaluate path.

## Safety

Optional tool-level `risk` (`read_only`, `external_write`, `destructive`,
`unknown`) and confirmation expectations. Missing risk defaults to `unknown`
(no false escalation). Broader safety/scope diffs are roadmap items (#87).

## Policies

Release knobs that map severities to CI failure
(`compatible` / `breaking` / `critical-only` / …). Config:
[config.md](config.md).

## Benchmarks / research

Corpus cases, splits (DEV/TEST/VERIFIED), mutations, and sensitivity harnesses
prove detectors without contaminating published scores. See ROADMAP Milestone
12+ and [AGENT_EXECUTION.md](AGENT_EXECUTION.md).

## DETECT · TEST · PROTECT

Product framing used in the README and [simple-explanation.md](simple-explanation.md):

1. **DETECT** — snapshots + structural diff  
2. **TEST** — probes (and later traces / eval)  
3. **PROTECT** — policies, Action, exit codes
