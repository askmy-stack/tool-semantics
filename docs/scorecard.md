# Compatibility scorecard

Human-readable scorecard and explanations for Tool-Semantics reports (#77).

## Dimensions

| Dimension | Source | Evidence |
| --- | --- | --- |
| Structural | Schema / tool / parameter / protocol codes | DETERMINISTIC |
| Semantic | Description / rename / soft constraint codes | DETERMINISTIC |
| Behavioral | `behavior.*` codes from model probes (#61) | MODEL-BASED |
| Safety | `tool.risk_changed` (and future safety codes) | DETERMINISTIC |
| Stability | `behavior.unstable_probe` / `deterministic_failure` | MODEL-BASED |

When behavioral or stability probes were **not** run, those dimensions are
**`n/a` with `score: null`** — never coerced to 0%.

## FINAL FAIL rules

Critical safety findings or any breaking/critical change force
`final_result = FAIL`, regardless of dimension averages. A single percentage
cannot hide a critical safety failure.

## Explanations

Each breaking/critical finding includes:

- What changed
- Why it matters
- Possible remediation hint
- Evidence label: `DETERMINISTIC` or `MODEL-BASED`

## Usage

```python
from tool_semantics.diff import compare_snapshots
from tool_semantics.scorecard import build_scorecard, render_scorecard_markdown

report = compare_snapshots(baseline, candidate)
card = build_scorecard(report, behavioral_ran=False, stability_ran=False)
print(render_scorecard_markdown(card))
```

`tool-semantics compare … --markdown-output` / `--json-output` include the
scorecard by default (`scorecard` key in JSON).

When `eval` (#76) and probe gates (#58) land, pass `probe_gate=` or
`behavioral_ran=True` so Behavioral/Stability flip from N/A to scored.
