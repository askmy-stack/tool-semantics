# GitHub Action

Composite action that compares two Tool-Semantics snapshots in CI and can post
the Markdown report as a pull-request comment.

## Location

```text
askmy-stack/tool-semantics/.github/actions/compare
```

## Versioning the Action

Pin the composite Action to a **release tag** (or commit SHA) so consumer CI stays
reproducible. Tags follow the package version (`v0.2.0`, …). A floating major pin
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
      - name: Capture baseline and candidate
        run: |
          pip install "tool-semantics==0.2.0"
          tool-semantics capture manifests/baseline.json -o .tool-semantics/baseline.json
          tool-semantics capture manifests/candidate.json -o .tool-semantics/candidate.json
      - uses: askmy-stack/tool-semantics/.github/actions/compare@v0.2.0
        with:
          baseline: .tool-semantics/baseline.json
          candidate: .tool-semantics/candidate.json
          config: .tool-semantics.toml
          policy: strict
          comment-on-pr: "true"
          upload-artifacts: "true"
```

## Inputs

| Input | Required | Default | Description |
| --- | --- | --- | --- |
| `baseline` | yes | — | Baseline snapshot path |
| `candidate` | yes | — | Candidate snapshot path |
| `config` | no | `""` | Optional ignore/policy config path |
| `policy` | no | `""` | `compatible` / `strict` / `critical-only` / `permissive` |
| `comment-on-pr` | no | `true` | Upsert a PR comment with the report |
| `upload-artifacts` | no | `false` | Upload the candidate snapshot and generated reports as a workflow artifact |
| `fail-on-breaking` | no | `true` | Legacy; `false` maps to `permissive` when `policy` unset |
| `working-directory` | no | `.` | Directory for install/compare |

## Outputs

| Output | Description |
| --- | --- |
| `compatible` | `true` / `false` after ignore rules (breaking/critical free) |
| `policy-failed` | `true` if the selected release policy failed |
| `report-path` | Path to the Markdown report artifact |

## Baselines and diagnostic artifacts

Commit the approved baseline snapshot to Git and treat it as the compatibility
contract. When `upload-artifacts: "true"`, the Action uploads the candidate
snapshot plus the generated Markdown and JSON reports in the
`tool-semantics-report` artifact. These files help diagnose a CI run; they do
not replace the Git-tracked baseline.

## Permissions

When `comment-on-pr` is enabled on `pull_request` events, the workflow needs
`pull-requests: write`.
