# ADR: Live MCP capture

## Status
Accepted (Milestone 1 initial implementation)

## Context
Static JSON manifests unlock deterministic CI, but real MCP servers expose tools
dynamically over stdio or SSE. Contributors need a capture path that:

1. Speaks enough of the MCP JSON-RPC protocol to list tools/prompts/resources
2. Normalizes results into `InterfaceSnapshot`
3. Redacts secret-like fields before snapshots are committed or uploaded

## Decision
- Ship **stdio** capture first (`tool-semantics capture-mcp -- <command>`).
- Use Content-Length framed JSON-RPC (LSP-style), matching common MCP servers.
- Treat prompts/resources as best-effort: missing methods do not fail capture.
- Redact by default (`--no-redact` to disable).
- Leave SSE as an explicit not-implemented error until a stable client lands.

## Consequences
- Tests use an in-repo fake stdio server (`tests/fixtures/fake_mcp_server.py`).
- Snapshot `protocol` is `mcp-stdio` for live captures.
- Consumers should still prefer checked-in manifests for hermetic CI when possible.
