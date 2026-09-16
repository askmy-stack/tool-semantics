# Downstream integrations

Tool-Semantics Milestone 4 metrics are intended for consumers in the
`askmy-stack` org. This doc is the handoff contract.

## myelinmesh — usage-weighted change risk

**Tracker:** [myelinmesh#21](https://github.com/askmy-stack/myelinmesh/issues/21)
(v0.4 project integrations). Tool-Semantics side of the handoff:
[#67](https://github.com/askmy-stack/tool-semantics/issues/67).

myelinmesh already ingests Tool-Semantics reports via adapter examples under
that repository. **Close #67** when myelinmesh can ingest the metrics JSON
below without further tool-semantics code changes — or open a dedicated API
issue if a new export field is required (do not expand this tracker).

### What to consume from tool-semantics ≥0.4.0

| Artifact | API | Use |
| --- | --- | --- |
| Probe metrics | `compute_probe_metrics(results)` → `ProbeMetrics` | Selection / argument / risk rates |
| Metrics JSON | `render_probe_metrics_json(metrics)` | Adapter / MER evidence payload |
| Metrics Markdown | `render_probe_metrics_markdown(metrics)` | Human-readable evidence |
| Stability | `run_probe_trials(...)` → `StabilityReport` | Separate unstable vs deterministic failures |
| Stability JSON | `render_stability_json(report)` | Machine-readable trial aggregates |

### `ProbeMetrics` field contract

| Field | Type | Notes |
| --- | --- | --- |
| `probe_count` | int | Probes considered |
| `evaluated_count` | int | Probes with a scored outcome |
| `missing_data_count` | int | Distinct from failures |
| `failed_evaluation_count` | int | Runner / eval errors |
| `tool_selection_accuracy` | float \| null | `null` when denominator empty — **not** `0.0` |
| `argument_validity_rate` | float \| null | same |
| `risk_compliance_rate` | float \| null | same |
| `confirmation_compliance_rate` | float \| null | same |
| `per_probe` | object | Per-probe detail map (opaque to ranking; optional evidence) |

### `StabilityReport` field contract

| Field | Type | Notes |
| --- | --- | --- |
| `trial_count` | int | Trials per probe |
| `seed` | int \| null | Repro seed when set |
| `summaries[]` | list | Per-probe trial rollups |
| `summaries[].probe_id` | str | |
| `summaries[].stability_score` | float | |
| `summaries[].unstable` | bool | High variance across trials |
| `summaries[].deterministic_failure` | bool | Fails every trial |
| `summaries[].aggregate_passed` | bool | |
| `summaries[].trials[]` | list | Individual trial rows |
| `metrics` | `ProbeMetrics` | Aggregate across trials |
| `runner` | object \| null | `RunnerMetadata` when model-backed |

`ProbeMetrics` distinguishes missing data from failed evaluations and uses
`None` rates when a denominator is empty — consumers must not treat missing
rates as `0.0`.

### Suggested fixture flow

1. Run offline or model-backed probes (`evaluate_probes` /
   `evaluate_probes_with_model`) against baseline and candidate snapshots.
2. Emit `render_probe_metrics_json` (+ optional `render_stability_json`).
3. Map into a myelinmesh MER record with `producer: "tool-semantics"`.
4. On the myelinmesh side, weight structural change severity by selection /
   argument failure rates when usage telemetry is available.

### Status checklist (for #67)

- [x] Export fields documented above match `probes.py` models
- [ ] Link myelinmesh adapter PR here when it lands
- [ ] Confirm ingest of metrics JSON without tool-semantics code changes
- [ ] If a new field is required → file a dedicated API issue (not this tracker)

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
