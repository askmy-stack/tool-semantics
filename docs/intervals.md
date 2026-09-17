# Confidence intervals for behavioral metrics (#115)

Do **not** treat tiny score differences as regressions when uncertainty is
large. Tool-Semantics attaches optional Wilson score intervals to model-backed
probe and stability reports.

## Display

```text
Baseline  89% ± 3%
Candidate 87% ± 4%   → overlapping → not a meaningful regression
```

Use `compare_rates()` before calling something a regression:

```python
from tool_semantics.intervals import compare_rates, wilson_interval

baseline = wilson_interval(89, 100)
candidate = wilson_interval(87, 100)
cmp = compare_rates(baseline, candidate, label="tool_selection_accuracy")
assert not cmp.meaningful_regression
print(cmp.warning)
# Overlapping confidence intervals (or insufficient n) — do not call this a regression…
```

A **meaningful regression** requires:

1. Both sides have `n >= min_n` (default **10**; raise for published claims)
2. Candidate interval lies entirely below the baseline interval (no overlap)

## Where intervals appear

| Surface | Field |
| --- | --- |
| Stability JSON (`--trials` > 1) | `intervals` on `StabilityReport` |
| Stability / model Markdown | `## Confidence intervals` section |
| Model probe JSON | `metrics.intervals` and top-level `intervals` |
| Library scorecard / eval hooks | `enrich_metrics_dict()`, `IntervalsBundle` |

Metrics include `tool_selection_accuracy`, `argument_validity_rate`,
`pass_rate`, plus when multi-trial: `pass_at_k_rate` / `pass_hat_k_rate`
(fraction of probes with ≥1 / all successes) and per-probe pass-rate CIs.

## Library

```python
from tool_semantics.intervals import (
    intervals_from_stability,
    pass_at_k_interval,
    wilson_interval,
)
from tool_semantics.probes import run_probe_trials

report = run_probe_trials(snapshot, probes, runner, trial_count=8, seed=1)
assert report.intervals is not None
print(report.intervals["metrics"])

ci = pass_at_k_interval([True, False, True, True], min_n=4)
print(ci.format_pm(), ci.format_bracket())
```

## Methodology notes

- Method: **Wilson score** interval (better coverage than naïve ±z·√(p̂(1−p̂)/n) near 0/1).
- Default confidence **0.95**; `sufficient_n` is false when `n < min_n`.
- Intervals are **informational** — they do not change exit codes by themselves.
- For eval / scorecard JSON, prefer `enrich_metrics_dict(metrics, results)` so
  consumers can show estimate ± half-width without inventing their own CI math.
