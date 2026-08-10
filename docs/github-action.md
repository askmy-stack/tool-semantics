# GitHub Action

Composite action that compares two Tool-Semantics snapshots in CI and can post
the Markdown report as a pull-request comment.

## Location

```text
askmy-stack/tool-semantics/.github/actions/compare
```

## Versioning the Action

Pin the composite Action to a **release tag** (or commit SHA) so consumer CI stays
reproducible. The Action has not been released under a version tag yet, so the
example below pins the current stable commit. After the first release, use the
matching version tag (`vX.Y.Z`); a floating major pin (`@v0`) can follow.

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
          pip install "tool-semantics @ git+https://github.com/askmy-stack/tool-semantics.git@64befaa9f65f825d75c6ce088d1f40e35054fdf0"
          tool-semantics capture manifests/baseline.json -o .tool-semantics/baseline.json
          tool-semantics capture manifests/candidate.json -o .tool-semantics/candidate.json
      - uses: askmy-stack/tool-semantics/.github/actions/compare@64befaa9f65f825d75c6ce088d1f40e35054fdf0
        with:
          baseline: .tool-semantics/baseline.json
          candidate: .tool-semantics/candidate.json
          config: .tool-semantics.toml
          policy: strict
          comment-on-pr: "true"
```

## Inputs

| Input | Required | Default | Description |
| --- | --- | --- | --- |
| `baseline` | yes | — | Baseline snapshot path |
| `candidate` | yes | — | Candidate snapshot path |
| `config` | no | `""` | Optional ignore/policy config path |
| `policy` | no | `""` | `compatible` / `strict` / `critical-only` / `permissive` |
| `comment-on-pr` | no | `true` | Upsert a PR comment with the report |
| `fail-on-breaking` | no | `true` | Legacy; `false` maps to `permissive` when `policy` unset |
| `working-directory` | no | `.` | Directory for install/compare |

## Outputs

| Output | Description |
| --- | --- |
| `compatible` | `true` / `false` after ignore rules (breaking/critical free) |
| `policy-failed` | `true` if the selected release policy failed |
| `report-path` | Path to the Markdown report artifact |

## Permissions

When `comment-on-pr` is enabled on `pull_request` events, the workflow needs
`pull-requests: write`.
