# Init and doctor

Developer experience commands for project scaffolding and sanity checks
([#85](https://github.com/askmy-stack/tool-semantics/issues/85),
[#96](https://github.com/askmy-stack/tool-semantics/issues/96)).

## `tool-semantics init`

Creates the standard [project layout](project-layout.md):

```bash
tool-semantics init
tool-semantics init --path ./services/mcp-gateway
tool-semantics init --force   # overwrite stub files
```

## `tool-semantics doctor`

Checks the environment and project without calling models or MCP tools by
default:

| Check | Hard fail? | Meaning |
| --- | --- | --- |
| `python` | yes | Requires 3.11+ |
| `install` | yes | Package importable |
| `config` | yes if present but invalid | Parses `.tool-semantics.toml` |
| `layout` | no | `.tool-semantics/` dirs present |
| `baselines` | yes if invalid JSON snapshots | Validates baseline files |
| `probes` | yes if suite fails to load | Loads discovered probe file |
| `model` | no | Warns when API key missing |
| `mcp` | no | Optional `--mcp-endpoint` HTTP reachability |

```bash
tool-semantics doctor
tool-semantics doctor --path ./my-service
tool-semantics doctor --mcp-endpoint https://example.com/mcp
```

Exit codes: `0` when there are no errors (warnings allowed), `1` on hard
failures.
