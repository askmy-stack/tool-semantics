# Lint and audit

Quality checks for tool names, descriptions, schemas, and risk declarations
([#97](https://github.com/askmy-stack/tool-semantics/issues/97)).

## `tool-semantics lint`

Per-tool findings:

| Code | Severity | Meaning |
| --- | --- | --- |
| `lint.missing_description` | error | Empty description |
| `lint.vague_description` | warning | Too short / placeholder phrasing |
| `lint.duplicate_description` | warning | Identical description on another tool |
| `lint.poor_name` | warning | Non-snake_case, too short, or generic |
| `lint.schema_description_mismatch` | warning | Description mentions undeclared params |
| `lint.risk_description_mismatch` | warning | Risk vs name/description hints disagree |
| `lint.unknown_risk` | info | Risk not declared |

```bash
tool-semantics capture examples/quality_bad_server.json -o .tool-semantics/bad.json
tool-semantics lint .tool-semantics/bad.json --markdown-output lint.md
```

## `tool-semantics audit`

Aggregates lint counts and lists top ambiguous tool pairs (token Jaccard on
name+description). When collision scoring (#79) lands, audit can consume those
scores; until then the built-in overlap heuristic is used.

```bash
tool-semantics audit .tool-semantics/bad.json --markdown-output audit.md
```

## Exit codes

| Code | Meaning |
| --- | --- |
| `0` | No errors (warnings allowed unless `--fail-on-warning`) |
| `1` | Errors present, or warnings with `--fail-on-warning` |
| `2` | Input / snapshot load failure |

`--fail-on-warning` is opt-in so teams can adopt lint gradually in CI.
