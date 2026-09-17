# Benchmark corpus (#92 / #116)

Offline behavioral compatibility cases with **DEV / TEST / VERIFIED**
partitions. See [docs/benchmarks.md](../docs/benchmarks.md).

## Partitions

| Split | Domains | Role |
| --- | --- | --- |
| `dev` | `toy-dev` | Calibrate heuristics only |
| `test` | `toy-test` | Default CI / PR gate |
| `verified` | `toy-verified` | Release / published research |

```bash
tool-semantics corpus                 # TEST (default)
tool-semantics corpus --split verified
```
