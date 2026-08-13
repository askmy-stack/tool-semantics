# Snapshot Storage and Provenance Design

## Goal

Make Tool-Semantics snapshots easy to retain, inspect, and trust across local
development, pull requests, and releases without introducing a database or
storing secrets.

## Scope

The first implementation adds three complementary storage paths:

1. **Git baselines:** users keep approved JSON snapshots in their repository.
2. **CI artifacts:** the composite GitHub Action can upload the candidate
   snapshot and compatibility reports from a workflow run.
3. **Provenance sidecar:** capture can optionally write a separate metadata
   document describing where and when the snapshot was captured and its
   SHA-256 content digest.

Object storage and a centralized snapshot registry are explicitly out of scope.
They require credentials, retention policy, access control, and an API that this
library does not yet own.

## User experience

### Trusted baseline in Git

Users capture and review a stable JSON baseline just as they do today:

```bash
tool-semantics capture manifests/server.json \
  -o .tool-semantics/baselines/production.json
```

The baseline is an ordinary JSON file that can be reviewed in pull requests,
versioned with Git tags, and used by the existing `compare` command.

### Provenance sidecar

`capture` and `capture-mcp` receive an optional `--provenance-output PATH`
option. It writes a sibling or user-selected JSON file such as:

```json
{
  "snapshot_path": ".tool-semantics/baselines/production.json",
  "snapshot_sha256": "…",
  "captured_at": "2026-08-13T00:00:00Z",
  "source": {
    "kind": "manifest",
    "location": "manifests/server.json"
  }
}
```

For live capture, `source.kind` is `mcp-stdio` or the future remote transport.
The source location contains a command or endpoint only after secret-like values
are redacted. Environment variables, authorization headers, and raw tokens are
never written.

The sidecar is deliberately separate from `InterfaceSnapshot`. Timestamp and
provenance values change between captures and must not create compatibility
diffs.

### CI artifacts

The composite compare Action receives optional inputs for a candidate snapshot
and a boolean `upload-artifacts` input, defaulting to `false`. When enabled, it
uploads the candidate snapshot, JSON report, and Markdown report as a GitHub
Actions artifact. It never uploads the baseline unless the workflow author
explicitly supplies it as the candidate path.

Artifacts are diagnostic outputs, not a source of truth. Git-tracked baselines
remain the official compatibility contract.

## Data and integrity

The SHA-256 value is computed from the exact bytes written to the snapshot file.
The provenance schema includes its own version field so it can evolve without
changing the snapshot schema. JSON is deterministic: keys are emitted in a
stable order and each file ends in one newline.

## Error handling

- A provenance write failure is treated like snapshot output failure: capture
  exits with code 2 and reports the path.
- Artifact upload is optional. If GitHub cannot upload it, the Action fails so
  the workflow author does not mistake a missing diagnostic for a saved one.
- Secrets in source metadata are redacted before serialization. Users retain
  `--no-redact` only for snapshot capture; provenance never writes supplied
  credentials.

## Testing

- Unit-test the provenance document for deterministic digest, source redaction,
  and stable serialization.
- CLI-test `--provenance-output` for manifest and stdio capture paths.
- Add an Action fixture or static validation for the artifact upload inputs and
  paths.
- Retain all existing snapshot and compare tests unchanged.

## Rollout

1. Ship provenance sidecars and optional CI artifacts in a minor release.
2. Document Git baselines as the recommended default.
3. Revisit object storage or a registry only after users need cross-repository
   retention and search.
