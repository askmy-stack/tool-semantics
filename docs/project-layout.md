# Project layout

Tool-Semantics uses a standard **`.tool-semantics/`** directory as the
behavioral baseline home for snapshots, probes, traces, and threshold stubs
([#85](https://github.com/askmy-stack/tool-semantics/issues/85)).

## Layout

```text
.tool-semantics.toml          # policy + ignore rules (project root)
.tool-semantics/
  README.md                   # short pointer for humans
  baselines/                  # reviewed baseline snapshots (check in)
    baseline.json
  candidate.json              # optional working candidate from capture
  probes/                     # probe fixtures (JSON/YAML)
    example.json
  behaviors.toml              # probe / stability threshold stubs
  traces/                     # agent traces for replay
```

Scaffold with:

```bash
tool-semantics init
# or: tool-semantics init --path ./my-service
```

Existing files are preserved unless you pass `--force`.

## Default discovery

When CLI flags are omitted, commands look under the cwd layout:

| Command | Default when flag omitted |
| --- | --- |
| `probe` | `--probes` → `.tool-semantics/probes/probes.json` or first `*.json` |
| `compare` | Still requires explicit baseline/candidate args (no silent compare) |
| `capture` | `-o` still defaults to `.tool-semantics/snapshot.json` |

Explicit path flags always win — discovery never overrides a provided path.

## Related

- Config schema: [config.md](config.md)
- Probes: [probes.md](probes.md)
- Adapters: [adapters.md](adapters.md)
- `init` / `doctor`: [dx.md](dx.md) · [#96](https://github.com/askmy-stack/tool-semantics/issues/96)
