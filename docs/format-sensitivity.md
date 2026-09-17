# Format-sensitivity fuzz testing (#111)

Measure whether **harmless schema formatting** changes alter model tool routing.
All transforms are documented as **meaning-preserving** — they must not change
tool names, types, required flags, or description *words*.

## CLI

```bash
# CI / local (FakeModelRunner — no network)
tool-semantics fuzz-format .tool-semantics/v1.json \
  --probes examples/probes/github_v1_offline.json \
  --fake \
  --threshold 0.05

# Opt-in live model
tool-semantics fuzz-format .tool-semantics/v1.json \
  --probes examples/probes/github_v1_offline.json \
  --model
```

Exit codes: `0` no warning, `1` format-sensitivity warning (delta > threshold),
`2` input error.

## Meaning-preserving transforms

| Transform | What changes |
| --- | --- |
| `property_order` | Key order inside parameter JSON Schema objects |
| `description_whitespace` | Collapse / expand whitespace in descriptions |
| `equivalent_json_schema` | Equivalent JSON Schema forms (`"string"` ↔ `["string"]`, `required` order) |
| `parameter_order` | Order of parameters on a tool |

Canonicalization (for tests) strips these presentation differences so variants
compare equal under `schemas_semantically_equal`.

## Library

```python
from tool_semantics.format_fuzz import (
    generate_format_variants,
    run_format_sensitivity,
    scripted_fake_factory,
)
from tool_semantics.runner import FakeModelRunner, ModelCompletion, ToolCallRequest, RunnerMetadata

variants = generate_format_variants(snapshot)
report = run_format_sensitivity(
    snapshot,
    probes,
    scripted_fake_factory(
        [
            ModelCompletion(
                tool_calls=[ToolCallRequest(name="search_issues", arguments={"query": "x"})],
                metadata=RunnerMetadata(provider="fake", model="fake"),
            )
        ]
    ),
    threshold=0.05,
)
assert report.passed  # Fake runners are format-insensitive
```

When `|Δ tool-selection accuracy|` exceeds the threshold, reports emit:

`FORMAT SENSITIVITY WARNING: …`

## CI policy

- Unit / CI tests **must** use `FakeModelRunner` / `--fake`.
- Live `--model` runs are opt-in and never required for merge gates.
