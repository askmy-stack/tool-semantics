# ADR: Live MCP capture

## Status
Accepted (Milestone 1 — stdio + SSE)

## Context
Static JSON manifests unlock deterministic CI, but real MCP servers expose tools
dynamically over stdio or SSE. Contributors need a capture path that:

1. Speaks enough of the MCP JSON-RPC protocol to list tools/prompts/resources
2. Normalizes results into `InterfaceSnapshot`
3. Redacts secret-like fields before snapshots are committed or uploaded

## Decision
- Ship **stdio** capture first (`tool-semantics capture-mcp -- <command>`).
- Ship **SSE** remote capture (`tool-semantics capture-mcp --sse <url>`) using
  the MCP SSE transport: GET `text/event-stream` for the `endpoint` event, then
  POST JSON-RPC to the message URL. Responses may arrive on the SSE stream or
  as direct POST JSON bodies.
- Auth via repeatable `--header 'Name: value'` (for example
  `Authorization: Bearer …`). Header **values** and secret-like header names are
  never written to snapshot metadata — only a redacted endpoint URL and
  non-secret header names are retained.
- Use Content-Length framed JSON-RPC (LSP-style) for stdio, matching common MCP servers.
- Treat prompts/resources as best-effort: missing methods do not fail capture.
- Redact by default (`--no-redact` to disable).

## Consequences
- Tests use in-repo fake servers (`tests/fixtures/fake_mcp_server.py`,
  `tests/fixtures/fake_mcp_sse_server.py`).
- Snapshot `protocol` is `mcp-stdio` or `mcp-sse` for live captures.
- Consumers should still prefer checked-in manifests for hermetic CI when possible.
