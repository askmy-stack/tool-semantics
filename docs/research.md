# Research harnesses

Opt-in experiment tooling for measuring how interface presentation affects
model tool selection. **Not part of default CI** — use Fake runners in unit
tests; live models only when explicitly opted in.

## Description / catalog sensitivity (#95)

Measure how much **tool description rewrite** or **catalog growth** is needed
before selection accuracy drops.

### Rewrite levels

| Level | Label | Transform |
| ---: | --- | --- |
| 0 | `original` | Unchanged descriptions |
| 1 | `light_paraphrase` | Deterministic synonym swaps |
| 2 | `shorten` | Keep roughly half the tokens |
| 3 | `expand` | Append instructional fluff |
| 4 | `severe` | Replace with opaque tokens (meaning stripped) |

### Catalog scaling

Pads the core snapshot with synthetic noise tools (same `synthesize_manifest`
pattern as discovery/bench helpers) at sizes `10, 25, 50, 100, 250` by default.

### CLI

```bash
# Description rewrite ladder (FakeModelRunner — no network)
tool-semantics sensitivity .tool-semantics/v1.json \
  --probes examples/probes/github_v1_offline.json \
  --mode description \
  --fake \
  --json-output /tmp/desc.json \
  --csv-output /tmp/desc.csv

# Catalog-size curve
tool-semantics sensitivity .tool-semantics/v1.json \
  --probes examples/probes/github_v1_offline.json \
  --mode catalog \
  --sizes 10,25,50 \
  --fake
```

Exit codes: `0` success, `2` input error. This command never fails the build on
accuracy drops — it exports research metrics only.

### Library

```python
from tool_semantics.sensitivity import (
    description_aware_factory,
    export_sensitivity_json,
    run_catalog_sensitivity,
    run_description_sensitivity,
)

desc = run_description_sensitivity(snapshot, probes, description_aware_factory)
catalog = run_catalog_sensitivity(snapshot, probes, description_aware_factory, sizes=(10, 50))
export_sensitivity_json(desc, Path("desc.json"))
```

`DescriptionAwareFakeRunner` selects the tool whose description tokens overlap
the probe intent most. When overlap is zero (e.g. severe rewrites), it picks a
deterministic fallback tool so selection accuracy is still measured — useful for
offline CI of the harness itself.

### Methodology caveats

- Synonym / shorten / expand transforms are **approximate**; they are not a
  claim that human-equivalent paraphrases behave the same under live models.
- Catalog padding adds synthetic tools, not real product surface area.
- Results are experiment outputs for notebooks / external analysis, not release
  gates unless a team explicitly wires them that way.
