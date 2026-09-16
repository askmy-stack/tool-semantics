# Benchmark corpus

Offline multi-domain behavioral compatibility cases (`benchmarks/`). Default
runs need **no network**: structural compare + offline probes against expected
detection codes.

## DEV / TEST / VERIFIED (#116)

Do **not** develop rules on the same tasks used for final evaluation.

| Partition | Purpose | When it runs |
| --- | --- | --- |
| **DEV** | Calibrate thresholds, rename heuristics, detector knobs | Local iteration only |
| **TEST** | Routine regression / PR CI (default) | Every PR (`TOOL_SEMANTICS_CORPUS_SPLIT=test`) |
| **VERIFIED** | Credible published / release results | Explicit release or research runs |

Partition map: [`benchmarks/splits.json`](../benchmarks/splits.json).

```bash
# CI default — TEST only
tool-semantics corpus
# or
TOOL_SEMANTICS_CORPUS_SPLIT=test tool-semantics corpus

# Calibrate on DEV (never publish these numbers as final)
tool-semantics corpus --split dev

# Release / research gate
TOOL_SEMANTICS_CORPUS_SPLIT=verified tool-semantics corpus --split verified
```

Guidance:

1. Tune thresholds on **DEV** only.
2. Gate PRs on **TEST** (or a fixed seed subset of TEST when large).
3. Quote **VERIFIED** scores in papers / release notes — after freezing the split.

See also [research.md](research.md).

## Layout

```
benchmarks/
  splits.json          # DEV / TEST / VERIFIED domain lists
  <domain>/
    baseline.json
    safe-change.json
    breaking-change.json
    probes.json
    expected-results.json
```

## Expected results schema

```json
{
  "safe_change": {
    "must_be_compatible": true,
    "forbidden_codes": ["tool.removed"],
    "offline_probes_must_pass": true
  },
  "breaking_change": {
    "must_be_compatible": false,
    "required_codes": ["tool.removed"],
    "required_subjects": ["search_items"]
  }
}
```

## Library

```python
from pathlib import Path
from tool_semantics.corpus import run_corpus, render_corpus_markdown
from tool_semantics.splits import load_splits_manifest, resolve_split

split = resolve_split()  # TEST unless TOOL_SEMANTICS_CORPUS_SPLIT is set
report = run_corpus(Path("benchmarks"), split=split)
assert report.passed, render_corpus_markdown(report)
```
