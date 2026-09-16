#!/usr/bin/env python3
"""Tiny demo MCP stdio server with interface variants for tutorials (#102).

Variants (pass as argv[1] or DEMO_MCP_VARIANT):
  v1            — baseline tools
  v2-safe       — additive / compatible changes only
  v2-breaking   — removed tool + required param
  v2-confusing  — near-duplicate tools that collide on selection
"""

from __future__ import annotations

import json
import os
import sys

VARIANTS = ("v1", "v2-safe", "v2-breaking", "v2-confusing")


def read_message() -> dict:
    header = b""
    while b"\r\n\r\n" not in header:
        chunk = sys.stdin.buffer.read(1)
        if not chunk:
            raise EOFError
        header += chunk
    content_length = None
    for line in header.decode().split("\r\n"):
        if line.lower().startswith("content-length:"):
            content_length = int(line.split(":", 1)[1].strip())
    if content_length is None:
        raise RuntimeError("missing content-length")
    body = sys.stdin.buffer.read(content_length)
    return json.loads(body.decode())


def write_message(payload: dict) -> None:
    raw = json.dumps(payload).encode()
    sys.stdout.buffer.write(f"Content-Length: {len(raw)}\r\n\r\n".encode() + raw)
    sys.stdout.buffer.flush()


def _tools_for(variant: str) -> list[dict]:
    search = {
        "name": "search_notes",
        "description": "Search personal notes by keyword.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
            },
            "required": ["query"],
        },
    }
    create = {
        "name": "create_note",
        "description": "Create a personal note.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "body": {"type": "string"},
            },
            "required": ["title", "body"],
        },
    }
    if variant == "v1":
        return [search, create]
    if variant == "v2-safe":
        # Additive: optional tag on create; new read-only list tool.
        create_safe = {
            **create,
            "inputSchema": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "body": {"type": "string"},
                    "tag": {"type": "string"},
                },
                "required": ["title", "body"],
            },
        }
        list_notes = {
            "name": "list_notes",
            "description": "List recent personal notes.",
            "inputSchema": {"type": "object", "properties": {}},
        }
        return [search, create_safe, list_notes]
    if variant == "v2-breaking":
        # Remove search_notes; require folder on create_note.
        create_breaking = {
            **create,
            "inputSchema": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "body": {"type": "string"},
                    "folder": {"type": "string"},
                },
                "required": ["title", "body", "folder"],
            },
        }
        return [create_breaking]
    if variant == "v2-confusing":
        # Keep search_notes but add a near-duplicate find_notes.
        find = {
            "name": "find_notes",
            "description": "Search personal notes by keyword.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                },
                "required": ["query"],
            },
        }
        return [search, find, create]
    raise ValueError(f"Unknown variant {variant!r}; expected one of {VARIANTS}")


def main() -> None:
    variant = (
        (sys.argv[1] if len(sys.argv) > 1 else None) or os.environ.get("DEMO_MCP_VARIANT") or "v1"
    )
    if variant not in VARIANTS:
        raise SystemExit(f"Unknown variant {variant!r}; expected one of {VARIANTS}")
    tools = _tools_for(variant)

    while True:
        try:
            message = read_message()
        except EOFError:
            return
        method = message.get("method")
        request_id = message.get("id")
        if method == "initialize":
            write_message(
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {"tools": {}},
                        "serverInfo": {"name": "demo-mcp", "version": variant},
                    },
                }
            )
        elif method == "notifications/initialized":
            continue
        elif method == "tools/list":
            write_message(
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {"tools": tools},
                }
            )
        elif method in {"prompts/list", "resources/list"}:
            key = "prompts" if method.startswith("prompts") else "resources"
            write_message({"jsonrpc": "2.0", "id": request_id, "result": {key: []}})
        elif request_id is not None:
            write_message(
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {"code": -32601, "message": f"Unknown method {method}"},
                }
            )


if __name__ == "__main__":
    main()
