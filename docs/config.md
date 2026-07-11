# Config

Tool-Semantics reads optional project config from `.tool-semantics.toml` in the
current working directory, or from an explicit `--config` path.

## Schema

```toml
[ignore]
codes = ["tool.description_changed", "parameter.default_changed"]
subjects = ["experimental_*", "*.debug"]
```

| Field | Type | Meaning |
| --- | --- | --- |
| `ignore.codes` | string array | Exact change codes to ignore (see [change-codes.md](change-codes.md)) |
| `ignore.subjects` | string array | `fnmatch` patterns against change subjects (`tool` or `tool.param`) |

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
