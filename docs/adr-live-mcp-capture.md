# ADR: Live MCP capture

## Status
Accepted (Milestone 1 — stdio + SSE; Milestone 7 — Streamable HTTP)

## Context
Static JSON manifests unlock deterministic CI, but real MCP servers expose tools
dynamically over stdio, legacy SSE, or Streamable HTTP. Contributors need a
capture path that:

1. Speaks enough of the MCP JSON-RPC protocol to list tools/prompts/resources
2. Negotiates / records protocol generation
3. Normalizes results into `InterfaceSnapshot`
4. Redacts secret-like fields before snapshots are committed or uploaded

## Decision
- Ship **stdio** capture (`tool-semantics capture-mcp -- <command>`).
- Ship **legacy SSE** remote capture (`tool-semantics capture-mcp --sse <url>`):
  GET `text/event-stream` for the `endpoint` event, then POST JSON-RPC to the
  message URL. Responses may arrive on the SSE stream or as direct POST JSON.
- Ship **Streamable HTTP** (`tool-semantics capture-mcp --http <url>`): POST
  JSON-RPC to a single MCP endpoint with
  `Accept: application/json, text/event-stream`. Honor `Mcp-Session-Id` and
  send `MCP-Protocol-Version` on post-initialize requests. Accept both JSON and
  SSE response bodies.
- Ship **bare-URL auto-detect** (`tool-semantics capture-mcp https://…/mcp`):
  try Streamable HTTP first; on transport mismatch fall back to legacy SSE.
  Auth failures and unsupported protocol versions do not fall back.
- Auth via repeatable `--header 'Name: value'`. Header **values** and
  secret-like header names are never written to snapshot metadata — only a
  redacted endpoint URL and non-secret header names are retained.
- Use Content-Length framed JSON-RPC (LSP-style) for stdio, matching common MCP servers.
- Prefer `2024-11-05` on stdio/SSE initialize and `2025-03-26` on Streamable
  HTTP; record the server’s negotiated `protocolVersion` when supported.
- Treat prompts/resources as best-effort: missing methods do not fail capture.
- Redact by default (`--no-redact` to disable).

## Consequences
- Tests use in-repo fake servers (`fake_mcp_server.py`, `fake_mcp_sse_server.py`,
  `fake_mcp_http_server.py`).
- Snapshot `protocol` is `mcp-stdio`, `mcp-sse`, or `mcp-http`.
- See [mcp-versions.md](mcp-versions.md) for supported generations.
- Consumers should still prefer checked-in manifests for hermetic CI when possible.
