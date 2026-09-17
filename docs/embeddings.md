# Embedding similarity (optional, #117)

Token-overlap diffs remain the **default** and require no embedding SDK.
An optional embedding layer sits between deterministic overlap and an LLM judge.

## Providers

| Provider | Install | Use |
| --- | --- | --- |
| `FakeEmbeddingProvider` | default (stdlib) | Deterministic CI / stub |
| Live providers | optional extras (future) | Opt-in only |

```python
from tool_semantics.embeddings import (
    FakeEmbeddingProvider,
    embedding_similarity,
    hybrid_tool_similarity,
    similarity_matrix,
)
from tool_semantics.diff import compare_snapshots
from tool_semantics.scanner import capture_manifest
from pathlib import Path

provider = FakeEmbeddingProvider()
baseline = capture_manifest(Path("examples/github_server_v1.json"))
candidate = capture_manifest(Path("examples/github_server_v2.json"))

# Optional: blend embeddings into rename detection
report = compare_snapshots(
    baseline,
    candidate,
    embedding_provider=provider,
    embedding_weight=0.5,
    rename_threshold=0.4,
)

score = embedding_similarity(baseline.tools[0], candidate.tools[0], provider)
assert score.source.value in {"MODEL-BASED", "HYBRID", "DETERMINISTIC"}
assert score.metadata is not None  # provider + model recorded
```

## Report labels

| `source` | Meaning |
| --- | --- |
| `DETERMINISTIC` | Token Jaccard only |
| `HYBRID` | Token + embedding blend |
| `MODEL-BASED` | Embedding cosine only |

Collision (#79) / rename confidence (#80) can consume `ToolSimilarityScore` when
those features are enabled.

Live embedding HTTP calls are **never** made unless a live provider is
constructed explicitly — CI uses `FakeEmbeddingProvider`.
