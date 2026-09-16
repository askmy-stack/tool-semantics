# MCP protocol versions

Tool-Semantics captures MCP interfaces across protocol generations without
assuming a single fixed version.

## Supported for capture

| Version | Typical transport | Notes |
| --- | --- | --- |
| `2024-11-05` | stdio, legacy HTTP+SSE | Preferred for stdio / `--sse` |
| `2025-03-26` | Streamable HTTP | Preferred for `--http` / bare URL |
| `2025-06-18` | Streamable HTTP | Same capture surface; `MCP-Protocol-Version` header on subsequent requests |
| `2025-11-25` | Streamable HTTP | Accepted when returned by `initialize` |

Negotiated `protocolVersion` is stored in snapshot metadata as
`protocol_version`, along with `transport` and `server_capabilities`. Auth
header **values** are never persisted.

`tool-semantics compare` / `eval` diff these fields when present on both
snapshots (`protocol.version_changed`, `transport.changed`,
`capability.added` / `removed` / `changed`) — see [change-codes.md](change-codes.md).

## Unsupported

Versions outside the table (for example experimental `2026-07-28` drafts) fail
capture with an actionable `Unsupported MCP protocol version` error listing
supported generations. Extend `SUPPORTED_PROTOCOL_VERSIONS` in
`mcp_capture.py` when a new generation is verified for tools/list capture.

## Remote transports

| CLI | Transport |
| --- | --- |
| `capture-mcp -- <cmd>` | stdio |
| `capture-mcp --http <url>` | Streamable HTTP |
| `capture-mcp --sse <url>` | Legacy SSE |
| `capture-mcp <https://…>` | Auto: Streamable HTTP, then SSE fallback |

Authentication failures (`401`/`403`) and unsupported protocol versions do
**not** fall back during auto-detect. Network / 404 / 405 / malformed responses
may fall back to legacy SSE per MCP client backwards-compatibility guidance.

## Error categories

Remote capture errors are prefixed for automation and clearer CLI UX:

| Prefix | Meaning |
| --- | --- |
| `[authentication]` | HTTP 401/403 or missing credentials |
| `[network]` | DNS / connection refused / transport errors |
| `[timeout]` | Deadline exceeded |
| `[protocol]` | HTTP 400 or other protocol-level HTTP failures |
| `[unsupported]` | Negotiated `protocolVersion` not in supported set |
| `[invalid_response]` | Empty / non-JSON / mismatched JSON-RPC body |
| `[unsupported_server]` | 404/405 endpoint, or both HTTP+SSE paths failed |
