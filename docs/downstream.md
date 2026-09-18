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

Optional live-capture smoke against the org MCP server (or any SSE MCP endpoint).
**Capture-only** — discovered tools are never executed.

### Manual / nightly recipe

```bash
export TOOL_SEMANTICS_DOGFOOD_SSE_URL="$MARKET_PULSE_SSE_URL"   # required
export TOOL_SEMANTICS_DOGFOOD_SSE_TOKEN="$TOKEN"                # if auth required

pip install "tool-semantics>=0.4.0"
# CLI path
tool-semantics capture-mcp --sse "$TOOL_SEMANTICS_DOGFOOD_SSE_URL" \
  --header "Authorization: Bearer $TOOL_SEMANTICS_DOGFOOD_SSE_TOKEN" \
  -o .tool-semantics/market-pulse.json

# Integration test (skipped in PR CI when env is unset)
pytest -m integration tests/test_dogfood_sse.py
```

Aliases accepted by the test: `MARKET_PULSE_SSE_URL`, `MARKET_PULSE_SSE_TOKEN` / `TOKEN`.

Optional GitHub Actions job (enable when repository secrets exist):

```yaml
# .github/workflows/dogfood-sse.yml
name: Dogfood SSE
on:
  workflow_dispatch:
  schedule:
    - cron: "0 6 * * 1"  # weekly Monday 06:00 UTC
jobs:
  capture:
    if: ${{ secrets.TOOL_SEMANTICS_DOGFOOD_SSE_URL != '' }}
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
      - uses: actions/setup-python@v7
        with:
          python-version: "3.12"
      - run: pip install -e ".[dev]"
      - run: pytest -m integration tests/test_dogfood_sse.py
        env:
          TOOL_SEMANTICS_DOGFOOD_SSE_URL: ${{ secrets.TOOL_SEMANTICS_DOGFOOD_SSE_URL }}
          TOOL_SEMANTICS_DOGFOOD_SSE_TOKEN: ${{ secrets.TOOL_SEMANTICS_DOGFOOD_SSE_TOKEN }}
```

Confirm:

- Snapshot protocol is `mcp-sse` (metadata `transport: sse`)
- Auth header **values** never appear in snapshot JSON / metadata (only header names)
- Tools list is non-empty and redaction still applies

Automated assertions live in [`tests/test_dogfood_sse.py`](../tests/test_dogfood_sse.py)
(`pytest.mark.integration`). Default PR CI does not set credentials, so the test
skips and stays green.

No market-pulse-mcp code changes are required for this dogfood path.
