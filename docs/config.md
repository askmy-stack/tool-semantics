# Config

Tool-Semantics reads optional project config from `.tool-semantics.toml` in the
current working directory, or from an explicit `--config` path.

## Schema

```toml
[ignore]
codes = ["tool.description_changed", "parameter.default_changed"]
subjects = ["experimental_*", "*.debug"]

[policy]
# Fail compare/CI when any change is at or above this severity.
# One of: info | warning | breaking | critical | none
fail_at_or_above = "breaking"

# Optional behavioral probe gate (issue #58). Omit [probes] to keep
# structural-only compare (current default).
[probes]
file = "probes/suite.json"   # JSON or YAML probe suite
target = "candidate"         # candidate | baseline | both
mode = "offline"             # offline | model
trials = 1                   # >1 implies model mode + stability
# seed = 42
# allow_unapproved = false

[probes.thresholds]
min_pass_rate = 1.0
# Model-backed metrics (omit to skip gating on that metric):
# min_tool_selection_accuracy = 1.0
# min_argument_validity_rate = 1.0
# min_stability_score = 1.0
fail_on_unstable = true
fail_on_deterministic_failure = true
```

| Field | Type | Meaning |
| --- | --- | --- |
| `ignore.codes` | string array | Exact change codes to ignore (see [change-codes.md](change-codes.md)) |
| `ignore.subjects` | string array | `fnmatch` patterns against change subjects (`tool` or `tool.param`) |
| `policy.fail_at_or_above` | string | Release gate threshold (default `breaking`) |
| `probes.file` | string | Probe suite path (relative to the config file directory) |
| `probes.target` | string | Which snapshot(s) to evaluate (default `candidate`) |
| `probes.mode` | string | `offline` (default) or `model` |
| `probes.trials` | int | Stability trials; `>1` forces model mode |
| `probes.thresholds.min_pass_rate` | float | Minimum fraction of probes that must pass (default `1.0`) |
| `probes.thresholds.min_tool_selection_accuracy` | float | Optional model metric floor |
| `probes.thresholds.min_argument_validity_rate` | float | Optional model metric floor |
| `probes.thresholds.min_stability_score` | float | Optional per-probe stability floor |
| `probes.thresholds.fail_on_unstable` | bool | Fail when any probe is unstable (default `true`) |
| `probes.thresholds.fail_on_deterministic_failure` | bool | Fail on deterministic probe failures (default `true`) |

## Severity model

Matched **warning / breaking / critical** changes are **downgraded to `info`** and
prefixed with `[ignored]` in the message. They remain visible in Markdown/JSON
reports and the CLI table, but no longer make `is_compatible` false or force
`compare` to exit `1`.

This lets teams adopt strict gates incrementally without hiding history.

## Probe gate

When `probes.file` is set (or `--probes` is passed to `compare`), Tool-Semantics
runs the suite after the structural diff and fails the release policy if
thresholds are breached. Offline mode needs no provider. Model mode requires
`TOOL_SEMANTICS_API_KEY` / `OPENAI_API_KEY` (exit `2` with guidance if missing).
A missing probe file is also exit `2`.

JSON reports include a `probes` object with per-target results, metrics /
stability summaries, and `policy.probe_failed`. See [probes.md](probes.md) and
[github-action.md](github-action.md).

## CLI

```bash
tool-semantics compare baseline.json candidate.json --config .tool-semantics.toml
# or rely on cwd discovery:
tool-semantics compare baseline.json candidate.json

# Opt-in probe gate without editing config:
tool-semantics compare baseline.json candidate.json \
  --probes probes/suite.json --probe-mode offline \
  --markdown-output report.md --json-output report.json
```
