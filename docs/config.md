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
detect_renames = true
rename_threshold = 0.55
# Opt-in: suppress tool.removed/tool.added for matched renames (legacy).
collapse_renames = false
use_embeddings = false
```

| Field | Type | Meaning |
| --- | --- | --- |
| `ignore.codes` | string array | Exact change codes to ignore (see [change-codes.md](change-codes.md)) |
| `ignore.subjects` | string array | `fnmatch` patterns against change subjects (`tool` or `tool.param`) |
| `policy.fail_at_or_above` | string | Release gate threshold (default `breaking`) |
| `diff.detect_renames` | bool | Emit `tool.renamed` candidates (default `true`) |
| `diff.rename_threshold` | float `[0,1]` | Minimum overall rename score (default `0.55`) |
| `diff.collapse_renames` | bool | When `true`, suppress matched `tool.removed`/`tool.added` (default `false`) |
| `diff.use_embeddings` | bool | Blend embedding cosine into rename score when a provider is registered |

### Rename confidence (#80)

Rename candidates combine documented Layer-1 weights:

| Signal | Weight |
| --- | ---: |
| parameter names | 0.35 |
| description tokens | 0.25 |
| name tokens | 0.20 |
| output schema | 0.20 |

Overall score maps to **LOW** (`< 0.60`), **MEDIUM** (`≥ 0.60`), or **HIGH** (`≥ 0.80`).
The `tool.renamed` message includes old→new, confidence, overall score, and per-signal
similarities. By default remove+add still appear; set `collapse_renames = true` to
treat a match as identity (legacy).


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
