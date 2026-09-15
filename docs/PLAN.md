# Course of action: tool-semantics (post–Milestone 4)

Status as of 2026-09-15: **Milestones 0–6 are shipped** on `main`, including
remote SSE capture (#43) and the model-backed probe stack (#44–#47) via
[PR #53](https://github.com/askmy-stack/tool-semantics/pull/53). First PyPI
release was `v0.2.0` (#31); provenance release `v0.3.0`; feature release
**`v0.4.0`** packages #43–#47.

For a short summary, see [CLAUDE.md](../CLAUDE.md). Roadmap checkboxes:
[ROADMAP.md](../ROADMAP.md).

## Completed phases

| Phase | Issues | Outcome |
| --- | --- | --- |
| 0 — Release hygiene | #31, `v0.3.0` | PyPI installable; Action pins work |
| 1 — Remote MCP | #43 | `capture-mcp --sse` + auth-safe headers |
| 2 — Model runner | #45 | `runner.py` (fake + OpenAI-compatible HTTP) |
| 3 — Probes / metrics / stability | #44 → #46 → #47 | Opt-in model probes, JSON/MD metrics, trials |
| 4 docs — Downstream handoff | — | See below + [downstream.md](downstream.md) |

## Remaining / next work

1. **Keep `main` green** — run `ruff format` / `ruff check` / `pytest` before merge.
2. **Downstream — myelinmesh v0.4** ([myelinmesh#21](https://github.com/askmy-stack/myelinmesh/issues/21)):
   consume Tool-Semantics probe metrics / stability JSON for usage-weighted
   change risk. Contract documented in [downstream.md](downstream.md).
3. **Optional dogfood** — SSE capture against market-pulse-mcp (commands in
   downstream.md).
4. **Dependabot** — only act when a dependency PR fails.

No further Milestone 1–4 product issues remain open once #43–#47 are closed.

## Cross-cutting rules

- Land changes via PR to `main`; keep code in existing module boundaries.
- Reuse `probes.py`, `report.py`, `redact.py`, `runner.py` rather than
  duplicating responsibilities.
- `pytest`, `ruff check .`, and `ruff format --check .` must pass.
