# Progressive tool-catalog discovery (#86)

Research / benchmark harness for measuring how tool-selection quality degrades
as catalogs grow, and for flagging **discovery regressions** when a candidate
adds many tools.

## Library API

```python
from tool_semantics.discovery import (
    CI_CATALOG_SIZES,
    DEFAULT_CATALOG_SIZES,
    SizeAwareFakeRunner,
    compare_discovery_curves,
    discovery_regression_changes,
    pad_catalog,
    run_discovery_curve,
)

curve = run_discovery_curve(
    snapshot,
    probes,
    runner,
    sizes=CI_CATALOG_SIZES,  # (10, 25, 50) for CI; use DEFAULT for full ladder
    require_approval=False,
)
report = compare_discovery_curves(
    baseline_curve,
    candidate_curve,
    baseline_tool_count=len(baseline.tools),
    candidate_tool_count=len(candidate.tools),
    accuracy_drop_threshold=0.10,
)
if report.has_regression:
    for change in discovery_regression_changes(report):
        print(change.code, change.message)
```

## Catalog padding

`pad_catalog(core, N)` keeps all core tools and fills to size `N` with synthetic
noise tools from `benchmarks.synthesize_manifest` (#14).

## Metrics per size

| Field | Meaning |
| --- | --- |
| `tool_selection_accuracy` | From `compute_probe_metrics` |
| `argument_validity_rate` | Same |
| `risk_compliance_rate` | Same |
| `elapsed_seconds` | Wall time for the probe batch at that size |

## Discovery regression

Emitted when candidate accuracy at a shared catalog size drops more than
`accuracy_drop_threshold` below the baseline curve **and** the candidate has
more tools than the baseline. Warning code: `discovery.accuracy_regression`.

## CI vs research

| Profile | Sizes |
| --- | --- |
| CI (`CI_CATALOG_SIZES`) | 10 / 25 / 50 + `SizeAwareFakeRunner` |
| Research (`DEFAULT_CATALOG_SIZES`) | 10 / 25 / 50 / 100 / 250 / 500; live model optional/nightly |

Live model runs are intentionally out of default CI (cost / flakiness).
