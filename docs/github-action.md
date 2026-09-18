# GitHub Action

Composite action that compares two Tool-Semantics snapshots in CI and can post
the Markdown report as a pull-request comment. Optionally gates on behavioral
probes (offline by default; model-backed when configured).

## Location

```text
askmy-stack/tool-semantics/.github/actions/compare
```

## Versioning the Action

Pin the composite Action to a **release tag** (or commit SHA) so consumer CI stays
reproducible. Tags follow the package version (`v0.4.0`, …). A floating major pin
such as `@v0` is fine once a `v0` moving tag exists; prefer an exact tag for
production workflows.

`@main` tracks the tip of the default branch and **may break** without notice —
use it only for local experiments.

After each GitHub Release, the tagged tree includes this composite Action, so
`uses: askmy-stack/tool-semantics/.github/actions/compare@vX.Y.Z` resolves from
that tag.

## Example consumer workflow

```yaml
name: Tool compatibility
on:
  pull_request:

permissions:
  contents: read
  pull-requests: write

jobs:
  compare:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      # .tool-semantics/baselines/github.json was captured, reviewed, and
      # committed before this pull request.
      - name: Capture candidate snapshot
        run: |
          pip install "tool-semantics==0.4.0"
          tool-semantics capture manifests/candidate.json -o .tool-semantics/candidate.json
      - uses: askmy-stack/tool-semantics/.github/actions/compare@v0.4.0
        with:
          baseline: .tool-semantics/baselines/github.json
          candidate: .tool-semantics/candidate.json
          policy: strict
          # Optional behavioral gate (offline; no API key required):
          probes: probes/suite.json
          probe-mode: offline
          comment-on-pr: "true"
          upload-artifacts: "true"
```

For model-backed gates, set `probe-mode: model` (and optionally `probe-trials`)
and provide `TOOL_SEMANTICS_API_KEY` / `OPENAI_API_KEY` as a repository secret
available to the job. Missing credentials or a missing probe file fail with
exit code `2`.

Probe thresholds and defaults can also live in `.tool-semantics.toml` — see
[config.md](config.md). Action inputs override the matching config fields.

## Inputs

| Input | Required | Default | Description |
| --- | --- | --- | --- |
| `baseline` | yes | — | Baseline snapshot path |
| `candidate` | yes | — | Candidate snapshot path |
| `config` | no | `""` | Optional ignore/policy/probe config path |
| `policy` | no | `""` | `compatible` / `strict` / `critical-only` / `permissive` |
| `probes` | no | `""` | Probe suite path; empty keeps structural-only behavior |
| `probe-mode` | no | `""` | `offline` or `model` (empty → config / offline default) |
| `probe-target` | no | `""` | `candidate` / `baseline` / `both` |
| `probe-trials` | no | `""` | Stability trial count (`>1` implies model mode) |
| `probe-seed` | no | `""` | Optional seed for model-backed trials |
| `comment-on-pr` | no | `true` | Upsert an eval-style PR comment (scorecard + optional probes) |
| `upload-artifacts` | no | `false` | Upload the candidate snapshot and generated reports as a workflow artifact |
| `fail-on-breaking` | no | `true` | Legacy; `false` maps to `permissive` when `policy` unset |
| `working-directory` | no | `.` | Directory for install/compare |

## Outputs

| Output | Description |
| --- | --- |
| `compatible` | `true` / `false` after ignore rules (breaking/critical free) |
| `policy-failed` | `true` if the selected release policy **or** probe gate failed |
| `probe-failed` | `true` if probe thresholds were breached (`false` when probes disabled) |
| `report-path` | Path to the Markdown report artifact |

## Baselines and diagnostic artifacts

Capture, review, and commit the approved baseline snapshot to Git before it is
used in CI; treat that file as the compatibility contract. A pull-request job
should capture only its candidate and compare it to the committed baseline, not
recreate the baseline during the run. To intentionally update the contract,
capture a new baseline, review its diff, and commit that snapshot change.

When `upload-artifacts: "true"`, the Action uploads the candidate snapshot plus
the generated Markdown and JSON reports in the `tool-semantics-report` artifact.
These files help diagnose a CI run; they do not replace the Git-tracked baseline.
When probes are enabled, the JSON report includes a `probes` section with
metrics / stability summaries.

## Permissions

When `comment-on-pr` is enabled on `pull_request` events, the workflow needs
`pull-requests: write`.

## PR comment shape

Comments are upserted with the marker `<!-- tool-semantics-report -->` and an
**eval-style** summary (not the raw full report alone):

```markdown
<!-- tool-semantics-report -->
## Tool-Semantics eval summary

**STATUS:** `FAIL`

### Counts

- critical: `0`
- breaking: `2`
- warning: `1`
- info: `3`

### Scorecard

| Dimension | Status | Score | Evidence |
| --- | --- | ---: | --- |
| `structural` | `fail` | 50% | `DETERMINISTIC` |
| `semantic` | `pass` | 100% | `DETERMINISTIC` |
| `behavioral` | `n/a` | n/a | `N/A` |
| `safety` | `pass` | 100% | `DETERMINISTIC` |
| `stability` | `n/a` | n/a | `N/A` |

_Behavioral / stability probes were not configured — structural-only summary
(behavioral/stability show n/a)._

### Top breaking findings

- `tool.removed` on `search_issues` (`DETERMINISTIC`) — Tool 'search_issues' was removed.

<details>
<summary>Full Tool-Semantics report</summary>

… full Markdown report including scorecard / probe sections …

</details>
```

When `probes` is set, the scorecard fills in behavioral (and optionally
stability) rows from the probe gate, and a probe failure forces
`STATUS: FAIL` even if structural policy would otherwise pass.