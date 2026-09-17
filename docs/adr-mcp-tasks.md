# ADR: MCP long-running task testing (stub)

**Status:** Proposed / deferred  
**Related:** [#91](https://github.com/askmy-stack/tool-semantics/issues/91)

## Context

Some MCP extensions expose long-running **task** operations (start, status,
complete, cancel). Behavioral compatibility for tasks differs from synchronous
`tools/call`: duration, cancellation, and intermediate status matter.

## Decision (first PR)

- **Do not** implement full task runtime orchestration yet.
- Capture/diff only the **advertisement** that task-related extensions exist
  (via `metadata.extensions` from `initialize`).
- Reserve follow-on work for a fixture harness that records:

  | Phase | Intent |
  | --- | --- |
  | `start` | Task accepted; returns task id |
  | `status` | Poll / stream progress without mutating success criteria |
  | `complete` | Terminal success / failure payload |
  | `cancel` | Cooperative cancellation observed |

## Consequences

- Extension removal for task-capable servers already surfaces as
  `extension.removed` (#91).
- A future issue can add `task.*` probe kinds and fake task servers without
  blocking extension diffs.

## Non-goals (this ADR)

- Live scheduling / worker pools
- Automatic execution of discovered task tools during compare
