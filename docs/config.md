# Config

Tool-Semantics reads optional project config from `.tool-semantics.toml` in the
current working directory, or from an explicit `--config` path.

## Schema

```toml
[ignore]
codes = ["tool.description_changed", "parameter.default_changed"]
subjects = ["experimental_*", "*.debug"]

[policy]
# Fail compare/CI when any change is at or above this severity.
# One of: info | warning | breaking | critical | none
fail_at_or_above = "breaking"

[diff]
# Detect confusable tool pairs in the candidate catalog (#79).
detect_collisions = true
collision_threshold = 0.55
# Optional Layer-2 embeddings (requires a registered provider).
use_embeddings = false
```

| Field | Type | Meaning |
| --- | --- | --- |
| `ignore.codes` | string array | Exact change codes to ignore (see [change-codes.md](change-codes.md)) |
| `ignore.subjects` | string array | `fnmatch` patterns against change subjects (`tool` or `tool.param`) |
| `policy.fail_at_or_above` | string | Release gate threshold (default `breaking`) |
| `diff.detect_collisions` | bool | Emit `tool.collision` warnings for high-overlap pairs (default `true`) |
| `diff.collision_threshold` | float `[0,1]` | Minimum confusability score to warn (default `0.55`) |
| `diff.use_embeddings` | bool | Blend Layer-2 embeddings when a provider is registered (default `false`) |

### Collision / confusability

Layer-1 (default) scores each unordered tool pair with the same weighted Jaccard
used for rename detection: parameter names (0.5) + description tokens (0.3) +
name tokens (0.2). Pairs at or above `collision_threshold` emit
`tool.collision` warnings (`TOOL COLLISION WARNING` in the message) with a score
in `[0, 1]`. Multi-tool connected components also emit a cluster warning.

Collisions are **warnings** — they do not fail CI unless
`policy.fail_at_or_above` is `warning` (or lower). Suppress with
`ignore.codes = ["tool.collision"]`.

Layer-2 embeddings are opt-in via `use_embeddings = true` and
`pip install 'tool-semantics[embeddings]'` plus
`tool_semantics.embeddings.register_provider(...)`. No embedding SDK is
bundled in the default install.


## Severity model

Matched **warning / breaking / critical** changes are **downgraded to `info`** and
prefixed with `[ignored]` in the message. They remain visible in Markdown/JSON
reports and the CLI table, but no longer make `is_compatible` false or force
`compare` to exit `1`.

This lets teams adopt strict gates incrementally without hiding history.

## CLI

```bash
tool-semantics compare baseline.json candidate.json --config .tool-semantics.toml
# or rely on cwd discovery:
tool-semantics compare baseline.json candidate.json
```
