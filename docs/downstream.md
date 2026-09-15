# Downstream integrations

Tool-Semantics Milestone 4 metrics are intended for consumers in the
`askmy-stack` org. This doc is the handoff contract.

## myelinmesh — usage-weighted change risk

**Tracker:** [myelinmesh#21](https://github.com/askmy-stack/myelinmesh/issues/21)
(v0.4 project integrations). myelinmesh already ingests Tool-Semantics reports
via adapter examples under that repository.

### What to consume from tool-semantics ≥0.4.0

| Artifact | API | Use |
| --- | --- | --- |
| Probe metrics | `compute_probe_metrics(results)` → `ProbeMetrics` | Selection / argument / risk rates |
| Metrics JSON | `render_probe_metrics_json(metrics)` | Adapter / MER evidence payload |
| Metrics Markdown | `render_probe_metrics_markdown(metrics)` | Human-readable evidence |
| Stability | `run_probe_trials(...)` → `StabilityReport` | Separate unstable vs deterministic failures |
| Stability JSON | `render_stability_json(report)` | Machine-readable trial aggregates |

`ProbeMetrics` distinguishes missing data from failed evaluations
(`missing_data_count`, `failed_evaluation_count`) and uses `None` rates when a
denominator is empty — consumers must not treat missing rates as `0.0`.

### Suggested fixture flow

1. Run offline or model-backed probes (`evaluate_probes` /
   `evaluate_probes_with_model`) against baseline and candidate snapshots.
2. Emit `render_probe_metrics_json` (+ optional `render_stability_json`).
3. Map into a myelinmesh MER record with `producer: "tool-semantics"`.
4. On the myelinmesh side, weight structural change severity by selection /
   argument failure rates when usage telemetry is available.

Open a **new** tool-semantics issue only if myelinmesh needs an export field
that is not covered by `ProbeMetrics` / `StabilityReport`.

## market-pulse-mcp — dogfood SSE capture

Optional live-capture smoke against the org MCP server:

```bash
pip install "tool-semantics>=0.4.0"
tool-semantics capture-mcp --sse "$MARKET_PULSE_SSE_URL" \
  --header "Authorization: Bearer $TOKEN" \
  -o .tool-semantics/market-pulse.json
```

Confirm:

- Snapshot protocol / metadata transport is SSE (`mcp-sse` / `sse`)
- Auth header values never appear in snapshot JSON / metadata
- Tools list is non-empty and redaction still applies

No market-pulse-mcp code changes are required for this dogfood path.
