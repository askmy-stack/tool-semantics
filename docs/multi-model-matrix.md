# Multi-model matrix & temperature sweeps (#94)

Formalize reproducibility metadata and config-driven multi-model / temperature
evaluation for model-backed probes.

## Repro fields (every cell)

| Field | Meaning |
| --- | --- |
| `provider` / `model` / `model_version` | Runner identity |
| `temperature` / `seed` / `trial_count` | Sampling controls |
| `snapshot_hash` / `probe_hash` | Content hashes (sha256 truncated) |
| `tool_semantics_version` | Library version |
| `prompt_tokens` / `completion_tokens` / `cost` | Optional when provider returns them |

## Library

```python
from tool_semantics.matrix import run_model_matrix, run_temperature_sweep, export_matrix_dataset
from tool_semantics.runner import FakeModelRunner, ModelCompletion, RunnerMetadata, ToolCallRequest


def factory(model, temperature, seed):
    return FakeModelRunner(
        [
            ModelCompletion(
                tool_calls=[ToolCallRequest(name="search_issues", arguments={"query": "x"})],
                metadata=RunnerMetadata(provider="fake", model=model),
            )
        ]
    )


report = run_model_matrix(
    snapshot,
    probes,
    models=["fake-a", "fake-b"],
    runner_factory=factory,
    temperatures=(0.0, 0.2, 0.5),
    seed=0,
)
export_matrix_dataset(report, Path("matrix-dataset.json"))
```

Temperature sweep helper defaults to **0 / 0.2 / 0.5**.

## CI

Unit tests use **FakeModelRunner** only. Live OpenAI-compatible runners remain
opt-in via existing `#60` adapters.

## Related

- Stability trials (#47)
- Runner interface (#45 / #60)
- Efficiency / cost metrics (#114)
