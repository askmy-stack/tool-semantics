# Course of action: tool-semantics roadmap to Milestone 4

This is the full, sequenced plan for closing out the remaining tool-semantics
roadmap, based on the current open-issue set (6 open issues, 0 open PRs as of
this writing) and [ROADMAP.md](../ROADMAP.md). For a short summary, see
[CLAUDE.md](../CLAUDE.md).

Milestones 0, 1, 2, 5, and 6 are shipped. Milestone 3 is mostly done (offline
probes, side-effect expectations); Milestone 4 (model matrix) is entirely
open. The plan below sequences the 6 open issues into four phases, each with
the agent role(s) needed to execute it.

## Phase 0 — Release unblock

**Issue:** [#31](https://github.com/askmy-stack/tool-semantics/issues/31) (p0)

**Why first:** `publish.yml` and trusted-publishing docs already exist
([docs/publishing.md](publishing.md)), but no GitHub Release has ever been
cut and README still says `# later: pip install tool-semantics`. Nothing
downstream — Action adoption, library users, even this plan's later phases —
matters if the package isn't installable.

**Scope:**
- One-time PyPI trusted publisher + `pypi` GitHub Environment (steps already
  documented in `docs/publishing.md`)
- Reconcile `version` in `pyproject.toml` and `src/tool_semantics/__init__.py`
- Move CHANGELOG.md Unreleased → dated `0.2.0` (or next) section
- Tag + GitHub Release `vX.Y.Z`, verify the publish workflow succeeds
- Update README install section to drop "later:" wording
- Verify `pip install tool-semantics` in a clean venv

**Required agent:** a single **implementation agent** (general-purpose).
This is a checklist execution task with an existing runbook
(`docs/publishing.md`) — no design ambiguity, so no Explore/Plan agent needed.

## Phase 1 — Remote MCP transport

**Issue:** [#43](https://github.com/askmy-stack/tool-semantics/issues/43)

**Scope:** SSE/remote MCP capture support, extending the existing local
stdio transport in `src/tool_semantics/mcp_capture.py`. Must produce the
same deterministic `InterfaceSnapshot` format as local capture, document the
supported transport(s) and auth boundary, reuse `src/tool_semantics/redact.py`
for secret-like metadata, and keep existing stdio behavior unchanged.

**Required agents:**
1. **Explore agent** — map the current stdio implementation in
   `mcp_capture.py` to find the right extension seam (transport
   abstraction vs. new function).
2. **Plan agent** — design the transport interface; this is the one phase
   with genuine design uncertainty (which remote transport(s) to support,
   how auth is passed without being treated as trusted metadata).
3. **Implementation agent** — build it against the Plan agent's design,
   with tests for success / invalid-endpoint / auth-error paths.

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

**Required agents:**
1. **Plan agent** — the interface design is the crux of this phase (getting
   the transport/evaluation separation and the "no forced SDK" constraint
   right up front avoids rework in Phase 3).
2. **Implementation agent** — builds the interface + one adapter, with
   fakes-based unit tests (no live model calls per the issue's acceptance
   criteria).

## Phase 3 — Model-backed probes, metrics, and stability

**Issues:** [#44](https://github.com/askmy-stack/tool-semantics/issues/44),
[#46](https://github.com/askmy-stack/tool-semantics/issues/46),
[#47](https://github.com/askmy-stack/tool-semantics/issues/47)

All three depend on the Phase 2 runner interface and are labeled
`research` — treat their acceptance criteria as a starting point, not a
fixed spec; re-scope after Phase 2 lands if the interface shape changes
assumptions.

- **#44** — human-reviewed probe format, opt-in model-backed execution
  layered onto existing offline probes, results recording selected
  tool/arguments/outcome/errors, offline behavior stays backward compatible.
- **#46** — tool-selection accuracy and argument-validity reporting, in both
  JSON and Markdown via the existing `src/tool_semantics/report.py`
  rendering rather than a new output path.
- **#47** — configurable repeated trials, per-trial + aggregate stability
  scoring, reports distinguishing unstable probes from deterministic
  failures.

**Required agents:** three **implementation agents**, one per issue, run
sequentially in the order above (#44 → #46 → #47), since #46's metrics and
#47's stability scoring both consume #44's probe execution results.

## Cross-cutting rules for every phase

- Run `pytest`, `ruff check .`, and the existing pre-commit hooks
  (`.pre-commit-config.yaml`) before considering a phase done — don't add
  new lint config.
- Every phase lands via a PR against `main`, never a direct push.
- Keep new code inside existing module boundaries listed in CLAUDE.md;
  reuse `probes.py`, `report.py`, and `redact.py` rather than duplicating
  their responsibilities in new files.
