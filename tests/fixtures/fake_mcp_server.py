#!/usr/bin/env python3
"""Minimal MCP stdio server fixture for Tool-Semantics capture tests."""

from __future__ import annotations

import json
import sys


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


def main() -> None:
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
                        "capabilities": {
                            "tools": {},
                            "prompts": {},
                            "resources": {},
                        },
                        "serverInfo": {"name": "fake-mcp", "version": "1.2.3"},
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
                    "result": {
                        "tools": [
                            {
                                "name": "echo",
                                "description": "Echo a message",
                                "inputSchema": {
                                    "type": "object",
                                    "properties": {
                                        "text": {"type": "string"},
                                        "api_key": {"type": "string"},
                                    },
                                    "required": ["text"],
                                },
                                "outputSchema": {
                                    "type": "object",
                                    "properties": {"text": {"type": "string"}},
                                },
                            }
                        ]
                    },
                }
            )
        elif method == "prompts/list":
            write_message(
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "prompts": [
                            {
                                "name": "summarize",
                                "description": "Summarize text",
                                "arguments": [{"name": "text", "required": True}],
                            }
                        ]
                    },
                }
            )
        elif method == "resources/list":
            write_message(
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "resources": [
                            {
                                "uri": "memo://secret-token",
                                "name": "memo",
                                "description": "A memo resource",
                                "mimeType": "text/plain",
                            }
                        ]
                    },
                }
            )
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
