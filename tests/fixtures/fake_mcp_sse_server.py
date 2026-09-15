"""Fake MCP SSE server for capture tests (stdlib only)."""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlparse

TOOLS = [
    {
        "name": "echo",
        "description": "Echo a message",
        "inputSchema": {
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        },
        "outputSchema": {"type": "object", "properties": {"text": {"type": "string"}}},
        "annotations": {"risk": "read_only"},
    }
]


class FakeMcpSseServer:
    def __init__(self, *, require_auth: bool = False) -> None:
        self.require_auth = require_auth
        self._httpd: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self.base_url = ""
        self.sse_url = ""

    def start(self) -> None:
        require_auth = self.require_auth

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
                return

            def _unauthorized(self) -> bool:
                if not require_auth:
                    return False
                if self.headers.get("Authorization") != "Bearer secret-token":
                    self.send_response(401)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(b'{"error":"unauthorized"}')
                    return True
                return False

            def do_GET(self) -> None:  # noqa: N802
                if self._unauthorized():
                    return
                if urlparse(self.path).path != "/sse":
                    self.send_response(404)
                    self.end_headers()
                    return
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Connection", "keep-alive")
                self.end_headers()
                host, port = self.server.server_address  # type: ignore[attr-defined]
                endpoint = f"http://{host}:{port}/message"
                self.wfile.write(f"event: endpoint\ndata: {endpoint}\n\n".encode())
                self.wfile.flush()
                # Hold the SSE connection open until server shutdown.
                while getattr(self.server, "is_running", False):
                    threading.Event().wait(0.1)

            def do_POST(self) -> None:  # noqa: N802
                if self._unauthorized():
                    return
                if urlparse(self.path).path != "/message":
                    self.send_response(404)
                    self.end_headers()
                    return
                length = int(self.headers.get("Content-Length", "0"))
                raw = self.rfile.read(length)
                try:
                    message = json.loads(raw.decode("utf-8"))
                except json.JSONDecodeError:
                    self.send_response(400)
                    self.end_headers()
                    return
                method = message.get("method")
                request_id = message.get("id")
                if method == "notifications/initialized":
                    self.send_response(202)
                    self.end_headers()
                    return
                if method == "initialize":
                    result: Any = {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {"tools": {}},
                        "serverInfo": {"name": "fake-sse-mcp", "version": "9.9.9"},
                    }
                elif method == "tools/list":
                    result = {"tools": TOOLS}
                elif method == "prompts/list":
                    result = {"prompts": []}
                elif method == "resources/list":
                    result = {"resources": []}
                else:
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(
                        json.dumps(
                            {
                                "jsonrpc": "2.0",
                                "id": request_id,
                                "error": {"code": -32601, "message": f"Unknown method {method}"},
                            }
                        ).encode()
                    )
                    return
                payload = {"jsonrpc": "2.0", "id": request_id, "result": result}
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(payload).encode())

        self._httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._httpd.is_running = True
        host, port = self._httpd.server_address
        self.base_url = f"http://{host}:{port}"
        self.sse_url = f"{self.base_url}/sse"
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._httpd is not None:
            self._httpd.is_running = False
            self._httpd.shutdown()
            self._httpd.server_close()
        if self._thread is not None:
            self._thread.join(timeout=2)
