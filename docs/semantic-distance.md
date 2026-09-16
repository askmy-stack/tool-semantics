# Semantic distance matrix and tool clustering (#82)

Help developers understand large MCP catalogs: pairwise similarity plus
SEARCH / WRITE / DESTRUCTIVE-style action families.

## Defaults

| Mode | Behavior |
| --- | --- |
| Deterministic (default) | Weighted token Jaccard (`diff._tool_similarity`) — same heuristic as rename detection |
| Embeddings (optional) | Blend token score with cosine similarity when an `EmbeddingProvider` is passed |
| N ≥ 500 | Pairwise matrix is **subsampled** unless `--allow-large` / `allow_large=True` |

Full pairwise cost is O(N²). For large catalogs prefer subsample or raise
`--max-tools`.

## Action families (heuristic)

| Family | Signals |
| --- | --- |
| `SEARCH` | `read_only` risk or name/description tokens like search/find/list/get |
| `WRITE` | `external_write` or create/update/write/send tokens |
| `DESTRUCTIVE` | `destructive` risk or delete/remove/drop tokens |
| `OTHER` | Everything else |

## CLI

```bash
tool-semantics capture examples/semantic/github_catalog.json -o snap.json
tool-semantics cluster snap.json --top 20
tool-semantics cluster snap.json --allow-large   # N≥500 full matrix
```

## Library

```python
from tool_semantics.scanner import capture_manifest
from tool_semantics.semantic import compute_semantic_matrix, render_semantic_matrix_markdown

snap = capture_manifest("examples/semantic/github_catalog.json")
report = compute_semantic_matrix(snap)
print(render_semantic_matrix_markdown(report))
```

## Related

- Tool collision / confusability (#79)
- Optional embeddings (#117)
