# Performance, caching, and cost (#100)

Optional scale harness, parallel model-backed probe workers, completion
caching, and token/cost summaries. **Timings are informational** — PR CI does
not gate on wall-clock numbers.

## Scale benchmark

```bash
# Full ladder (host-dependent)
python scripts/bench_scale.py

# Smaller local check
python scripts/bench_scale.py --sizes 10,100,500 --json
```

Sizes default to **10 / 100 / 500 / 1000 / 5000** tools. Each size times:

1. Snapshot build (`synthesize_manifest` → `snapshot_from_manifest`)
2. Structural compare
3. Offline probe evaluation

Library:

```python
from tool_semantics.benchmarks import run_scale_benchmark, render_scale_benchmark_markdown

rows = run_scale_benchmark((10, 100))
print(render_scale_benchmark_markdown(rows))
```

## Parallel workers

```bash
tool-semantics probe snap.json --probes probes.json --model --workers 4
```

Results are always ordered like the input probe list (`concurrent.futures.map`).
Shared runners are locked when `workers > 1` so scripted / non-thread-safe
runners stay correct; live HTTP runners still benefit when cache misses dominate.

## Completion cache

```bash
tool-semantics probe snap.json --probes probes.json --model \
  --cache-dir .tool-semantics/cache
```

Cache key material:

- model id
- system + user prompt
- tools schema hash
- snapshot hash
- temperature + seed

JSON reports include `cache: { hits, misses, stores, hit_rate }` and per-result
`cache_hit`.

## Cost / tokens

When provider responses include OpenAI-style `usage` on `ModelCompletion.raw`,
reports attach:

```json
"cost": {
  "prompt_tokens": 120,
  "completion_tokens": 40,
  "total_tokens": 160,
  "calls_with_usage": 3,
  "calls_missing_usage": 0,
  "estimated_cost_usd": null
}
```

USD estimates appear only when you pass rates into `summarize_costs(...)`.
