"""Fake MCP Streamable HTTP server for capture tests (stdlib only)."""

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


class FakeMcpHttpServer:
    """Minimal Streamable HTTP MCP endpoint (JSON responses, optional session)."""

    def __init__(
        self,
        *,
        require_auth: bool = False,
        protocol_version: str = "2025-03-26",
        use_session: bool = True,
        respond_sse: bool = False,
        unsupported_protocol: bool = False,
    ) -> None:
        self.require_auth = require_auth
        self.protocol_version = protocol_version
        self.use_session = use_session
        self.respond_sse = respond_sse
        self.unsupported_protocol = unsupported_protocol
        self._httpd: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self.base_url = ""
        self.mcp_url = ""
        self._session_id = "test-session-abc123"

    def start(self) -> None:
        require_auth = self.require_auth
        protocol_version = self.protocol_version
        use_session = self.use_session
        respond_sse = self.respond_sse
        unsupported_protocol = self.unsupported_protocol
        session_id = self._session_id

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

            def _check_session(self, *, initializing: bool) -> bool:
                if not use_session or initializing:
                    return True
                if self.headers.get("Mcp-Session-Id") != session_id:
                    self.send_response(400)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(b'{"error":"missing session"}')
                    return False
                return True

            def do_POST(self) -> None:  # noqa: N802
                if self._unauthorized():
                    return
                if urlparse(self.path).path != "/mcp":
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
                initializing = method == "initialize"

                if method == "notifications/initialized":
                    if not self._check_session(initializing=False):
                        return
                    self.send_response(202)
                    self.end_headers()
                    return

                if not self._check_session(initializing=initializing):
                    return

                if method == "initialize":
                    if unsupported_protocol:
                        self.send_response(400)
                        self.send_header("Content-Type", "application/json")
                        self.end_headers()
                        self.wfile.write(
                            json.dumps(
                                {
                                    "jsonrpc": "2.0",
                                    "id": request_id,
                                    "error": {
                                        "code": -32602,
                                        "message": "UnsupportedProtocolVersion",
                                        "data": {"supported": ["2099-01-01"]},
                                    },
                                }
                            ).encode()
                        )
                        return
                    requested = (message.get("params") or {}).get("protocolVersion")
                    # Echo a known modern version; ignore exotic requests.
                    negotiated = protocol_version
                    if requested == "2099-01-01":
                        negotiated = "2099-01-01"
                    result: Any = {
                        "protocolVersion": negotiated,
                        "capabilities": {"tools": {}, "prompts": {}},
                        "serverInfo": {"name": "fake-http-mcp", "version": "2.0.0"},
                    }
                elif method == "tools/list":
                    result = {"tools": TOOLS}
                elif method == "prompts/list":
                    result = {
                        "prompts": [
                            {
                                "name": "greet",
                                "description": "Say hello",
                                "arguments": [],
                            }
                        ]
                    }
                elif method == "resources/list":
                    result = {
                        "resources": [
                            {
                                "uri": "memo://notes",
                                "name": "notes",
                                "description": "Notes",
                                "mimeType": "text/plain",
                            }
                        ]
                    }
                else:
                    payload = {
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "error": {"code": -32601, "message": f"Unknown method {method}"},
                    }
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps(payload).encode())
                    return

                payload = {"jsonrpc": "2.0", "id": request_id, "result": result}
                if respond_sse and method != "initialize":
                    self.send_response(200)
                    self.send_header("Content-Type", "text/event-stream")
                    if use_session and initializing:
                        self.send_header("Mcp-Session-Id", session_id)
                    self.end_headers()
                    self.wfile.write(f"event: message\ndata: {json.dumps(payload)}\n\n".encode())
                    return

                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                if use_session and initializing:
                    self.send_header("Mcp-Session-Id", session_id)
                self.end_headers()
                self.wfile.write(json.dumps(payload).encode())

            def do_GET(self) -> None:  # noqa: N802
                # Streamable HTTP servers may reject GET with 405 when no SSE listen.
                self.send_response(405)
                self.end_headers()

            def do_DELETE(self) -> None:  # noqa: N802
                self.send_response(200)
                self.end_headers()

        self._httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._httpd.is_running = True
        host, port = self._httpd.server_address
        self.base_url = f"http://{host}:{port}"
        self.mcp_url = f"{self.base_url}/mcp"
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._httpd is not None:
            self._httpd.is_running = False
            self._httpd.shutdown()
            self._httpd.server_close()
        if self._thread is not None:
            self._thread.join(timeout=2)
