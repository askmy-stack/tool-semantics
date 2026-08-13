# Snapshot storage final-fix report

## Changes

- Provenance command sanitization now redacts secret-like option names including
  `--auth=…` and `--bearer-token=…`, plus secret-bearing environment assignments
  such as `API_TOKEN=…`. This provenance-specific protection remains active even
  when capture uses `--no-redact`.
- Capture and capture-mcp reject equal or equivalent snapshot/provenance paths
  before writing, preserving an existing snapshot.
- The compare Action validates that the candidate, Markdown report, and JSON
  report all exist before its explicitly opted-in artifact upload. Candidate path
  resolution continues to use the requested working directory.
- Applied the exact Ruff formatting changes required in the snapshot-storage
  plan, provenance module, and Action regression test.
- P1 re-review follow-up: all command-form `NAME=value` environment assignments
  are redacted, including names such as `GITHUB_PAT` and `AWS_ACCESS_KEY_ID`.
  The Action upload step now requires the successful outcome of the complete
  artifact-path validation step while retaining `always()` for failed compares.

## Verification

- `python -m pytest --cov=tool_semantics --cov-report=term-missing`: 54 passed;
  total coverage 88%.
- `ruff check .`: passed.
- `ruff format --check .`: passed (41 files already formatted).
- `mypy src`: passed with no issues in 14 source files.
- `python -m build`: passed; built sdist and wheel.
- `git diff --check`: passed.

## Implementation commit

`657f9b44ba901722d30f43a5e6beee865799b6b8` (`fix snapshot storage review findings`)

## P1 re-review follow-up commit

`e4729635e0fd961466fd56523a8e05cff4a5a6fd` (`harden snapshot artifact and provenance checks`)
