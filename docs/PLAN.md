# Course of action: tool-semantics roadmap to Milestone 4

This is the full, sequenced plan for closing out the remaining tool-semantics
roadmap, based on the current open-issue set (5 open issues as of 2026-09-15)
and [ROADMAP.md](../ROADMAP.md). For a short summary, see
[CLAUDE.md](../CLAUDE.md).

Milestones 0, 2, 5, and 6 are shipped. Milestone 1 is mostly done (stdio live;
SSE/remote remaining). Milestone 3 is mostly done (offline probes, side-effect
expectations). Milestone 4 (model matrix) is entirely open. First PyPI release
`v0.2.0` ([#31](https://github.com/askmy-stack/tool-semantics/issues/31)) is
**done**; `main` carries 0.3.0 metadata that still needs a GitHub Release tag.

## Phase 0 — Release hygiene (`v0.3.0`)

**Status:** code + CHANGELOG on `main`; GitHub Release / PyPI `0.3.0` still
missing. Docs already pin `@v0.3.0`.

**Scope:**
- Tag + GitHub Release `v0.3.0` (triggers `publish.yml`)
- Verify `pip install tool-semantics==0.3.0` in a clean venv
- Keep Action pin examples in [github-action.md](github-action.md) aligned

**Required agent:** ops / maintainer with Release write access (see
[publishing.md](publishing.md)).

## Phase 1 — Remote MCP transport

**Issue:** [#43](https://github.com/askmy-stack/tool-semantics/issues/43)

**Scope:** SSE/remote MCP capture support, extending the existing local
stdio transport in `src/tool_semantics/mcp_capture.py`. Must produce the
same deterministic `InterfaceSnapshot` format as local capture, document the
supported transport(s) and auth boundary, reuse `src/tool_semantics/redact.py`
for secret-like metadata, and keep existing stdio behavior unchanged.

## Phase 2 — Provider-neutral model runner

**Issue:** [#45](https://github.com/askmy-stack/tool-semantics/issues/45)

**Why this order:** #45 is the foundation #44, #46, and #47 all depend on —
building any of them first would mean redoing them once the runner interface
lands.

**Scope:** a runner interface that separates provider transport from probe
evaluation, at least one provider adapter behind it, model/provider/version
and run-config metadata recorded in results, configurable timeouts/retries/
cost limits, and — critically — no required provider SDK dependency for
users who only want the deterministic offline checks. Extend, don't replace,
`src/tool_semantics/probes.py` (`Probe`, `ProbeKind`, `evaluate_probes`).

## Phase 3 — Model-backed probes, metrics, and stability

**Issues:** [#44](https://github.com/askmy-stack/tool-semantics/issues/44),
[#46](https://github.com/askmy-stack/tool-semantics/issues/46),
[#47](https://github.com/askmy-stack/tool-semantics/issues/47)

Execute sequentially (#44 → #46 → #47):

- **#44** — human-reviewed probe format, opt-in model-backed execution
  layered onto existing offline probes, results recording selected
  tool/arguments/outcome/errors, offline behavior stays backward compatible.
- **#46** — tool-selection accuracy and argument-validity reporting, in both
  JSON and Markdown via the existing `src/tool_semantics/report.py`
  rendering rather than a new output path.
- **#47** — configurable repeated trials, per-trial + aggregate stability
  scoring, reports distinguishing unstable probes from deterministic
  failures.

## Phase 4 — Downstream

- **myelinmesh** v0.4: usage-weighted Tool-Semantics change risk (tracked on
  myelinmesh #21 / ROADMAP). Depends on #46 metrics shape.
  - Fixture shape to consume: `ProbeMetrics` / stability JSON from
    `tool_semantics.report.render_probe_metrics_json` and
    `StabilityReport.model_dump()`.
  - Open a linking issue on tool-semantics only if myelinmesh needs an extra
    export field beyond these metrics.
- Optional dogfood: remote capture against **market-pulse-mcp**:

  ```bash
  tool-semantics capture-mcp --sse "$MARKET_PULSE_SSE_URL" \
    -H "Authorization: Bearer $TOKEN" \
    -o .tool-semantics/market-pulse.json
  ```

## Cross-cutting rules for every phase

- Run `pytest`, `ruff check .`, and the existing pre-commit hooks
  (`.pre-commit-config.yaml`) before considering a phase done — don't add
  new lint config.
- Every phase lands via a PR against `main`, never a direct push.
- Keep new code inside existing module boundaries listed in CLAUDE.md;
  reuse `probes.py`, `report.py`, and `redact.py` rather than duplicating
  their responsibilities in new files.
