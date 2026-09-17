# Benchmark corpus (#92)

Public multi-domain behavioral compatibility cases. Default runs are **offline**
(no network): compare + offline probes against expected detection codes.

## Layout

```
benchmarks/
  <domain>/
    baseline.json
    safe-change.json
    breaking-change.json
    probes.json
    expected-results.json
```

Stubbed domains keep only a `README.md` until filled.

## Domains

| Domain | Status |
| --- | --- |
| `github` | full |
| `filesystem` | full |
| `database` | full |
| `messaging` | stub |
| `project-management` | stub |
| `generic` | stub |

## Expected results schema

```json
{
  "safe_change": {
    "must_be_compatible": true,
    "forbidden_codes": ["tool.removed"],
    "offline_probes_must_pass": true
  },
  "breaking_change": {
    "must_be_compatible": false,
    "required_codes": ["tool.removed"],
    "required_subjects": ["search_issues"]
  }
}
```

## Run

```bash
# Library / pytest (CI)
pytest tests/test_corpus.py -q

# CLI
tool-semantics corpus
```

Missed expected detections fail the run (exit 1).

## Adding a case

1. Create `benchmarks/<domain>/` with the five required files.
2. Keep safe changes compatible (optional params, description tweaks).
3. Put at least one breaking signal in `breaking-change.json` and list its
   `required_codes` / `required_subjects` in `expected-results.json`.
4. Add offline probes that pass on `baseline.json`.
5. Run `pytest tests/test_corpus.py` locally (no network).
