# Research metrics

Project-specific research instrumentation. These metrics support internal
evaluation and paper-style reporting; they are **not** marketed as universal
capability claims.

## Behavioral Compatibility Horizon (#110)

METR-inspired question: *at what workflow step-complexity does compatibility
begin to fail?*

### Measurable complexity (not human-time)

| Signal | Use |
| --- | --- |
| Step count | Tool calls / workflow steps in a successful trajectory |
| Tools available | Catalog size at decision time (optional future) |
| State transitions | Distinct state keys touched |
| Ambiguity / risk | From difficulty metadata when present (#109) |

This release buckets observations by **step-complexity** into canonical sizes
`1 / 3 / 5 / 10 / 20`.

### Methodology

1. Collect `(step_complexity, passed[, trial_count])` observations from probes
   or workflow evals.
2. Map each observation to the nearest canonical bucket (ceil toward harder).
3. Publish per-bucket success rates only when `observations ≥ min_samples`
   (default **5**).
4. Estimate **80%** and **50%** horizons by linear interpolation between
   adjacent *adequate* buckets where the success rate crosses the target from
   above. **Omit** estimates when sample size is inadequate or no crossing
   exists.
5. When total trials permit (default ≥ **20**), attach Wilson 95% confidence
   intervals on bucket rates and a conservative CI band on horizon steps.

### Library

```python
from tool_semantics.horizon import (
    HorizonObservation,
    compute_compatibility_horizon,
    render_horizon_markdown,
)

observations = [
    HorizonObservation(probe_id="a", step_complexity=1, passed=True, trial_count=4),
    HorizonObservation(probe_id="b", step_complexity=10, passed=False, trial_count=4),
    # …
]
report = compute_compatibility_horizon(observations)
print(report.horizon_80.steps, report.horizon_50.steps)
print(render_horizon_markdown(report))
```

### Reporting guidance

- Always show the methodology disclaimer in reports.
- Prefer omitting a horizon over publishing a thin-sample number.
- Pair with difficulty/messiness grouping (#109) and pass@k (#106) when those
  layers are available — horizon answers *where* failure starts; pass@k
  answers *how reliably*.

## Related

- [#109](https://github.com/askmy-stack/tool-semantics/issues/109) difficulty / messiness
- [#106](https://github.com/askmy-stack/tool-semantics/issues/106) pass@k / pass^k
- [#92](https://github.com/askmy-stack/tool-semantics/issues/92) multi-domain corpus
- [`docs/reliability.md`](reliability.md) when present on reliability branches
