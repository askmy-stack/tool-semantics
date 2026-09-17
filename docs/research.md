# Research hygiene

## Corpus splits (#116)

Published behavioral results must not reuse the same tasks that tuned the
detectors. Tool-Semantics partitions corpus domains into:

- **DEV** — calibrate thresholds and heuristics
- **TEST** — default CI / PR gate
- **VERIFIED** — release and research publication only

Details and CLI: [benchmarks.md](benchmarks.md). Manifest:
`benchmarks/splits.json`.

Never present DEV scores as final. Prefer VERIFIED (or a pre-registered TEST
subset) when quoting numbers externally.

## Related research tracks

Description/catalog sensitivity, mutations, multi-model matrix, and horizon
metrics should declare which split they used and keep VERIFIED runs opt-in.
