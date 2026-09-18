# ADR: Optional centralized snapshot registry

## Status

Proposed (design only — **not** implemented in the core `tool-semantics`
package). Tracker: [#63](https://github.com/askmy-stack/tool-semantics/issues/63).

## Context

Teams often want **shared approved baselines** across multiple repositories
(platform MCP servers consumed by several product apps). Today the supported
paths are:

1. **Git baselines** — reviewed JSON under `.tool-semantics/` (or similar)
2. **CI artifacts** — per-run uploads from the compare Action
3. **Provenance sidecars** — local metadata + content digest next to a snapshot

A centralized registry (object storage + API) would help multi-repo orgs, but it
introduces auth, retention, tenancy, and operational ownership that do not
belong in the core library install.

Related: [snapshot storage design](superpowers/specs/2026-08-13-snapshot-storage-design.md),
[live MCP capture ADR](adr-live-mcp-capture.md), [downstream](downstream.md).

## Decision

### Recommendation

**Stay with Git baselines as the default and supported path.** Treat a
centralized registry as an **optional companion service** (separate package or
org-internal service), not a dependency of `pip install tool-semantics`.

### Non-goals for the core library

- No database, object-store client, or network registry API in the default
  install
- No long-lived cloud credentials required for capture / compare / probe
- No multi-tenant ACL engine inside this repository
- No automatic promotion of unreviewed candidate snapshots to “approved”

### If a companion registry is built later

| Concern | Proposal |
| --- | --- |
| **Content addressing** | Store immutable snapshot blobs keyed by SHA-256 of canonical JSON (same digest as provenance sidecars). Names/tags are mutable pointers. |
| **Auth** | Short-lived OIDC / workload identity for CI; PAT or SSO for humans. Never embed tokens in snapshot JSON (continue redaction rules). |
| **Retention** | Default: keep content-addressed blobs ≥ 90 days; approved tags indefinitely until explicitly retired. Soft-delete with tombstones. |
| **Relationship to Git** | Registry is a **cache / distribution** layer. Git remains the review surface for policy-critical baselines. Provenance sidecars reference both `git_sha` (when known) and `content_digest`. |
| **API surface** | Minimal: `PUT blob`, `GET blob`, `PUT/GET ref` (e.g. `org/server@approved`). Compare continues to take local paths; a thin CLI helper may `pull` refs into `.tool-semantics/`. |
| **Compatibility** | Blobs are ordinary `InterfaceSnapshot` JSON — no proprietary envelope required beyond optional registry metadata outside the blob. |

### Explicit out-of-scope for this ADR

Implementing the registry service in-repo. File a follow-up issue only after
design approval and a clear owning team.

## Consequences

- Core Tool-Semantics stays offline-first and credential-light.
- Orgs that need shared baselines either (a) publish a small internal
  baseline repo, or (b) build/host a companion registry that speaks content-
  addressed snapshot blobs.
- Provenance digests already provide the hook for content addressing without
  changing the snapshot schema.

## Alternatives considered

1. **Ship MinIO/S3 helpers in-core** — rejected; pulls cloud SDKs and secrets
   into the default dependency graph.
2. **Only Git submodules / shared baseline repos** — accepted as the
   recommended near-term pattern; no new service required.
3. **Embed a SQLite registry in the CLI** — rejected for multi-repo sharing;
   fine as a local cache later if needed, but not a “centralized” registry.
