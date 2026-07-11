# GitHub Action

Composite action that compares two Tool-Semantics snapshots in CI and can post
the Markdown report as a pull-request comment.

## Location

```text
askmy-stack/tool-semantics/.github/actions/compare
```

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
          pip install "tool-semantics @ git+https://github.com/askmy-stack/tool-semantics.git"
          tool-semantics capture manifests/baseline.json -o .tool-semantics/baseline.json
          tool-semantics capture manifests/candidate.json -o .tool-semantics/candidate.json
      - uses: askmy-stack/tool-semantics/.github/actions/compare@main
        with:
          baseline: .tool-semantics/baseline.json
          candidate: .tool-semantics/candidate.json
          config: .tool-semantics.toml
          comment-on-pr: "true"
          fail-on-breaking: "true"
```

## Inputs

| Input | Required | Default | Description |
| --- | --- | --- | --- |
| `baseline` | yes | — | Baseline snapshot path |
| `candidate` | yes | — | Candidate snapshot path |
| `config` | no | `""` | Optional ignore-config path |
| `comment-on-pr` | no | `true` | Upsert a PR comment with the report |
| `fail-on-breaking` | no | `true` | Fail the job on exit code 1 |
| `working-directory` | no | `.` | Directory for install/compare |

## Outputs

| Output | Description |
| --- | --- |
| `compatible` | `true` / `false` after ignore rules |
| `report-path` | Path to the Markdown report artifact |

## Permissions

When `comment-on-pr` is enabled on `pull_request` events, the workflow needs
`pull-requests: write`.
