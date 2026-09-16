# Efficiency metrics (#114)

Track operational cost alongside correctness. **Efficiency never replaces
correctness** in pass/fail — it only surfaces regressions for review.

## Metrics

| Field | Meaning |
| --- | --- |
| `tool_call_count` | Total tool calls |
| `failed_call_count` | Failed / errored calls |
| `retry_count` | Retries / re-attempts |
| `latency_ms` | Aggregate model/tool latency |
| `wall_clock_ms` | End-to-end duration |
| `prompt_tokens` / `completion_tokens` | Optional token usage |
| `model_cost` / `currency` | Optional provider cost |

## Usage

```python
from tool_semantics.efficiency import (
    EfficiencyMetrics,
    append_efficiency_section,
    compare_efficiency,
    load_efficiency_pair,
    render_efficiency_markdown,
)

baseline, candidate = load_efficiency_pair("examples/efficiency/sample_metrics.json")
report = compare_efficiency(baseline, candidate)
assert report.has_regression
assert report.affects_pass_fail is False
print(render_efficiency_markdown(report))
# Attach to any eval / probe markdown when metrics exist:
print(append_efficiency_section("# Eval report\n", report))
```

Relative deltas are easy to read (e.g. tool calls `8→31`, latency `+94%`).
Default regression thresholds: +50% for calls/retries/failures, latency,
tokens, and cost (override via `*_regression_ratio` kwargs).

Cost / token fields are omitted from comparison when absent on both sides.
Fixture: [`examples/efficiency/sample_metrics.json`](../examples/efficiency/sample_metrics.json).
