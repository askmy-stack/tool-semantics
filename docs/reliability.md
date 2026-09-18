# Reliability metrics (pass@k / pass^k)

Repeated model-backed probe trials expose first-class reliability metrics
beyond average accuracy (#106).

| Metric | Meaning |
| --- | --- |
| **pass@k** | At least one of `k` trials succeeded for the probe |
| **pass^k** (`pass_hat_k` in JSON) | Every one of `k` trials succeeded |
| **pass_rate** | Fraction of trials that passed for the probe |
| **pass_variance** | Bernoulli variance of the empirical pass rate |
| **stability_score** | Consistency of selected tool + args across trials (#47) |

Unstable probes (varying selections) are distinguished from **deterministic
failures** (same wrong outcome every trial).

## CLI

```bash
export TOOL_SEMANTICS_API_KEY=…
tool-semantics probe .tool-semantics/v1.json \
  --probes examples/probes/github_v1_offline.json \
  --trials 4 --seed 1 \
  --markdown-output stability.md --json-output stability.json
```

`--trials` sets `k`. `--seed` makes runs reproducible when the provider honors it.

## Library

```python
from tool_semantics.probes import run_probe_trials

report = run_probe_trials(snapshot, probes, runner, trial_count=4, seed=1)
print(report.reliability.pass_at_k_rate)  # fraction of probes with ≥1 success
print(report.reliability.pass_hat_k_rate)  # fraction with all successes
for summary in report.summaries:
    print(summary.probe_id, summary.pass_at_k, summary.pass_hat_k, summary.pass_rate)
```

JSON includes `reliability` and per-probe `pass_at_k` / `pass_hat_k` /
`pass_rate` / `pass_variance` alongside existing stability fields.

## Eval

When `tool-semantics eval` (#76) runs with `--probe-trials` > 1, the stability
section should surface the same `reliability` block (see stacked eval work).
