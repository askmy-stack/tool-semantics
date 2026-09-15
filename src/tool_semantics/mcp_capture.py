from __future__ import annotations

import json
import os
import select
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

from tool_semantics.models import (
    InterfaceSnapshot,
    PromptContract,
    ResourceContract,
    RiskLevel,
    ToolContract,
)
from tool_semantics.redact import redact_snapshot
from tool_semantics.scanner import ManifestError, _normalize_parameters

# Auth / secret header names must never land in snapshot metadata.
_AUTH_HEADER_NAMES = frozenset(
    {
        "authorization",
        "proxy-authorization",
        "x-api-key",
        "api-key",
        "cookie",
        "set-cookie",
    }
)


class McpCaptureError(ManifestError):
    """Raised when a live MCP capture fails."""


def _read_message(stdout: Any, timeout: float) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    header = b""
    while b"\r\n\r\n" not in header:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise McpCaptureError("Timed out waiting for MCP message headers")
        ready, _, _ = select.select([stdout], [], [], remaining)
        if not ready:
            raise McpCaptureError("Timed out waiting for MCP message headers")
        chunk = stdout.read(1)
        if not chunk:
            raise McpCaptureError("MCP server closed stdout while reading headers")
        header += chunk
    header_text = header.decode("utf-8", errors="replace")
    content_length = None
    for line in header_text.split("\r\n"):
        if line.lower().startswith("content-length:"):
            content_length = int(line.split(":", 1)[1].strip())
            break
    if content_length is None:
        raise McpCaptureError("MCP message missing Content-Length header")
    body = b""
    while len(body) < content_length:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise McpCaptureError("Timed out waiting for MCP message body")
        ready, _, _ = select.select([stdout], [], [], remaining)
        if not ready:
            raise McpCaptureError("Timed out waiting for MCP message body")
        chunk = stdout.read(content_length - len(body))
        if not chunk:
            raise McpCaptureError("MCP server closed stdout while reading body")
        body += chunk
    payload = json.loads(body.decode("utf-8"))
    if not isinstance(payload, dict):
        raise McpCaptureError("MCP message root must be an object")
    return payload


def _write_message(stdin: Any, payload: dict[str, Any]) -> None:
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    stdin.write(f"Content-Length: {len(raw)}\r\n\r\n".encode() + raw)
    stdin.flush()


def _rpc(
    stdin: Any,
    stdout: Any,
    request_id: int,
    method: str,
    params: dict[str, Any] | None = None,
    timeout: float = 10.0,
) -> Any:
    message: dict[str, Any] = {"jsonrpc": "2.0", "id": request_id, "method": method}
    if params is not None:
        message["params"] = params
    _write_message(stdin, message)
    while True:
        response = _read_message(stdout, timeout=timeout)
        if response.get("id") != request_id:
            # Ignore notifications / unrelated traffic.
            continue
        if "error" in response:
            raise McpCaptureError(f"MCP error for {method}: {response['error']}")
        return response.get("result")


def _tool_from_mcp(raw: dict[str, Any]) -> ToolContract:
    name = raw.get("name")
    if not isinstance(name, str) or not name:
        raise McpCaptureError("MCP tool is missing a string name")
    input_schema = raw.get("inputSchema") or {"type": "object", "properties": {}}
    if not isinstance(input_schema, dict):
        raise McpCaptureError(f"Tool '{name}' inputSchema must be an object")
    output_schema = raw.get("outputSchema")
    if output_schema is not None and not isinstance(output_schema, dict):
        raise McpCaptureError(f"Tool '{name}' outputSchema must be an object")
    risk_raw = None
    annotations = raw.get("annotations")
    if isinstance(annotations, dict):
        risk_raw = annotations.get("risk")
    try:
        risk = RiskLevel(risk_raw) if isinstance(risk_raw, str) else RiskLevel.UNKNOWN
    except ValueError:
        risk = RiskLevel.UNKNOWN
    return ToolContract(
        name=name,
        description=str(raw.get("description", "")),
        parameters=_normalize_parameters(input_schema),
        output_schema=output_schema,
        risk=risk,
    )


def _prompt_from_mcp(raw: dict[str, Any]) -> PromptContract:
    name = raw.get("name")
    if not isinstance(name, str) or not name:
        raise McpCaptureError("MCP prompt is missing a string name")
    raw_arguments = raw.get("arguments")
    arguments: list[Any] = raw_arguments if isinstance(raw_arguments, list) else []
    return PromptContract(
        name=name,
        description=str(raw.get("description", "")),
        arguments=[arg for arg in arguments if isinstance(arg, dict)],
    )


def _resource_from_mcp(raw: dict[str, Any]) -> ResourceContract:
    uri = raw.get("uri")
    name = raw.get("name")
    if not isinstance(uri, str) or not uri:
        raise McpCaptureError("MCP resource is missing a string uri")
    if not isinstance(name, str) or not name:
        name = uri
    return ResourceContract(
        uri=uri,
        name=name,
        description=str(raw.get("description", "")),
        mime_type=raw.get("mimeType") if isinstance(raw.get("mimeType"), str) else None,
    )


def capture_mcp_stdio(
    command: list[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    timeout: float = 15.0,
    server_name: str | None = None,
    redact: bool = True,
) -> InterfaceSnapshot:
    """Connect to an MCP server over stdio and capture tools/prompts/resources."""
    if not command:
        raise McpCaptureError("MCP command must not be empty")
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    try:
        process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=str(cwd) if cwd else None,
            env=merged_env,
            bufsize=0,
        )
    except OSError as exc:
        raise McpCaptureError(f"Failed to start MCP server: {exc}") from exc

    assert process.stdin is not None
    assert process.stdout is not None
    try:
        init = _rpc(
            process.stdin,
            process.stdout,
            1,
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "tool-semantics", "version": "0.1.0"},
            },
            timeout=timeout,
        )
        _write_message(process.stdin, {"jsonrpc": "2.0", "method": "notifications/initialized"})
        tools_result = _rpc(process.stdin, process.stdout, 2, "tools/list", {}, timeout=timeout)
        prompts: list[PromptContract] = []
        resources: list[ResourceContract] = []
        try:
            prompts_result = _rpc(
                process.stdin, process.stdout, 3, "prompts/list", {}, timeout=timeout
            )
            raw_prompts = (
                prompts_result.get("prompts", []) if isinstance(prompts_result, dict) else []
            )
            prompts = [_prompt_from_mcp(item) for item in raw_prompts if isinstance(item, dict)]
        except McpCaptureError:
            prompts = []
        try:
            resources_result = _rpc(
                process.stdin, process.stdout, 4, "resources/list", {}, timeout=timeout
            )
            raw_resources = (
                resources_result.get("resources", []) if isinstance(resources_result, dict) else []
            )
            resources = [
                _resource_from_mcp(item) for item in raw_resources if isinstance(item, dict)
            ]
        except McpCaptureError:
            resources = []

        raw_tools = tools_result.get("tools", []) if isinstance(tools_result, dict) else []
        if not isinstance(raw_tools, list):
            raise McpCaptureError("tools/list result.tools must be an array")
        tools = [_tool_from_mcp(item) for item in raw_tools if isinstance(item, dict)]
        server_info = init.get("serverInfo", {}) if isinstance(init, dict) else {}
        resolved_name = (
            server_name
            or (server_info.get("name") if isinstance(server_info, dict) else None)
            or command[0]
        )
        snapshot = InterfaceSnapshot(
            protocol="mcp-stdio",
            server_name=str(resolved_name),
            server_version=(
                str(server_info.get("version"))
                if isinstance(server_info, dict) and server_info.get("version") is not None
                else None
            ),
            tools=sorted(tools, key=lambda tool: tool.name),
            prompts=sorted(prompts, key=lambda prompt: prompt.name),
            resources=sorted(resources, key=lambda resource: resource.uri),
            metadata={"transport": "stdio", "command": command},
        )
        return redact_snapshot(snapshot) if redact else snapshot
    finally:
        process.terminate()
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()


def _safe_endpoint_for_metadata(url: str) -> str:
    """Strip userinfo / query / fragment so auth material is not persisted."""
    parsed = urlparse(url)
    host = parsed.netloc.split("@")[-1]
    return urllib.parse.urlunparse((parsed.scheme, host, parsed.path, "", "", ""))


def _filter_request_headers(headers: dict[str, str] | None) -> dict[str, str]:
    if not headers:
        return {}
    return {
        key: value
        for key, value in headers.items()
        if isinstance(key, str) and isinstance(value, str)
    }


def _headers_for_metadata(headers: dict[str, str]) -> list[str]:
    """Record only non-secret header *names* (never values)."""
    names: list[str] = []
    for key in sorted(headers):
        if key.lower() in _AUTH_HEADER_NAMES or "token" in key.lower() or "secret" in key.lower():
            continue
        if key.lower() in {"authorization", "cookie"}:
            continue
        names.append(key)
    return names


class _SseSession:
    """Minimal MCP SSE client: GET event stream + POST JSON-RPC to message endpoint."""

    def __init__(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        timeout: float = 15.0,
    ) -> None:
        if not url or not isinstance(url, str):
            raise McpCaptureError("SSE URL must be a non-empty string")
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise McpCaptureError(f"Invalid SSE endpoint URL: {url!r}")
        self._url = url
        self._headers = _filter_request_headers(headers)
        self._timeout = timeout
        self._message_url: str | None = None
        self._pending: dict[int, dict[str, Any]] = {}
        self._lock = threading.Lock()
        self._endpoint_ready = threading.Event()
        self._error: BaseException | None = None
        self._closed = False
        self._response: Any = None
        self._thread = threading.Thread(target=self._read_loop, name="mcp-sse-reader", daemon=True)

    def start(self) -> None:
        self._thread.start()
        if not self._endpoint_ready.wait(timeout=self._timeout):
            self.close()
            if self._error is not None:
                raise McpCaptureError(str(self._error)) from self._error
            raise McpCaptureError(f"Timed out waiting for SSE endpoint event from {self._url!r}")
        if self._error is not None:
            self.close()
            raise McpCaptureError(str(self._error)) from self._error
        if not self._message_url:
            self.close()
            raise McpCaptureError("SSE stream ended before providing a message endpoint")

    def close(self) -> None:
        self._closed = True
        if self._response is not None:
            try:
                self._response.close()
            except Exception:  # noqa: BLE001 — best-effort teardown
                pass

    def _read_loop(self) -> None:
        request = urllib.request.Request(
            self._url,
            headers={
                "Accept": "text/event-stream",
                "Cache-Control": "no-cache",
                **self._headers,
            },
            method="GET",
        )
        try:
            self._response = urllib.request.urlopen(request, timeout=self._timeout)
        except urllib.error.HTTPError as exc:
            self._error = McpCaptureError(
                f"SSE authentication/HTTP error {exc.code} for {self._url!r}: {exc.reason}"
            )
            self._endpoint_ready.set()
            return
        except urllib.error.URLError as exc:
            self._error = McpCaptureError(
                f"Failed to connect to SSE endpoint {self._url!r}: {exc.reason}"
            )
            self._endpoint_ready.set()
            return
        except Exception as exc:  # noqa: BLE001
            self._error = McpCaptureError(f"Failed to open SSE stream: {exc}")
            self._endpoint_ready.set()
            return

        event_name = "message"
        data_lines: list[str] = []
        try:
            while not self._closed:
                line_bytes = self._response.readline()
                if not line_bytes:
                    break
                line = line_bytes.decode("utf-8", errors="replace").rstrip("\r\n")
                if line == "":
                    if data_lines:
                        self._dispatch_event(event_name, "\n".join(data_lines))
                    event_name = "message"
                    data_lines = []
                    continue
                if line.startswith(":"):
                    continue
                if line.startswith("event:"):
                    event_name = line[6:].strip() or "message"
                elif line.startswith("data:"):
                    data_lines.append(line[5:].lstrip())
        except Exception as exc:  # noqa: BLE001
            if not self._closed and self._error is None:
                self._error = McpCaptureError(f"SSE stream read failed: {exc}")
        finally:
            self._endpoint_ready.set()

    def _dispatch_event(self, event_name: str, data: str) -> None:
        if event_name == "endpoint":
            endpoint = data.strip()
            if not endpoint:
                self._error = McpCaptureError("SSE endpoint event contained an empty URL")
                self._endpoint_ready.set()
                return
            self._message_url = urljoin(self._url, endpoint)
            self._endpoint_ready.set()
            return
        if event_name != "message":
            return
        try:
            payload = json.loads(data)
        except json.JSONDecodeError:
            return
        if not isinstance(payload, dict):
            return
        request_id = payload.get("id")
        if not isinstance(request_id, int):
            return
        with self._lock:
            self._pending[request_id] = payload

    def rpc(self, request_id: int, method: str, params: dict[str, Any] | None = None) -> Any:
        if self._message_url is None:
            raise McpCaptureError("SSE message endpoint is not ready")
        message: dict[str, Any] = {"jsonrpc": "2.0", "id": request_id, "method": method}
        if params is not None:
            message["params"] = params
        body = json.dumps(message, separators=(",", ":")).encode("utf-8")
        request = urllib.request.Request(
            self._message_url,
            data=body,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
                **self._headers,
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as response:
                # Some servers return the JSON-RPC result directly from POST.
                raw = response.read()
                if raw:
                    try:
                        direct = json.loads(raw.decode("utf-8"))
                    except json.JSONDecodeError:
                        direct = None
                    if isinstance(direct, dict) and direct.get("id") == request_id:
                        if "error" in direct:
                            raise McpCaptureError(f"MCP error for {method}: {direct['error']}")
                        return direct.get("result")
        except urllib.error.HTTPError as exc:
            raise McpCaptureError(
                f"SSE message POST failed with HTTP {exc.code} for {method}: {exc.reason}"
            ) from exc
        except urllib.error.URLError as exc:
            raise McpCaptureError(f"SSE message POST failed for {method}: {exc.reason}") from exc

        deadline = time.monotonic() + self._timeout
        while time.monotonic() < deadline:
            with self._lock:
                if request_id in self._pending:
                    response_payload = self._pending.pop(request_id)
                    if "error" in response_payload:
                        raise McpCaptureError(
                            f"MCP error for {method}: {response_payload['error']}"
                        )
                    return response_payload.get("result")
            if self._error is not None:
                raise McpCaptureError(str(self._error)) from self._error
            time.sleep(0.01)
        raise McpCaptureError(f"Timed out waiting for SSE response to {method}")

    def notify(self, method: str, params: dict[str, Any] | None = None) -> None:
        if self._message_url is None:
            raise McpCaptureError("SSE message endpoint is not ready")
        message: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            message["params"] = params
        body = json.dumps(message, separators=(",", ":")).encode("utf-8")
        request = urllib.request.Request(
            self._message_url,
            data=body,
            headers={
                "Content-Type": "application/json",
                **self._headers,
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout):
                return
        except urllib.error.HTTPError as exc:
            # Notifications may be accepted with empty bodies; treat auth errors as fatal.
            if exc.code in {401, 403}:
                raise McpCaptureError(
                    f"SSE authentication/HTTP error {exc.code} for notification {method}"
                ) from exc
        except urllib.error.URLError as exc:
            raise McpCaptureError(
                f"SSE notification POST failed for {method}: {exc.reason}"
            ) from exc


def _snapshot_from_lists(
    *,
    protocol: str,
    server_name: str,
    server_version: str | None,
    tools: list[ToolContract],
    prompts: list[PromptContract],
    resources: list[ResourceContract],
    metadata: dict[str, Any],
    redact: bool,
) -> InterfaceSnapshot:
    snapshot = InterfaceSnapshot(
        protocol=protocol,
        server_name=server_name,
        server_version=server_version,
        tools=sorted(tools, key=lambda tool: tool.name),
        prompts=sorted(prompts, key=lambda prompt: prompt.name),
        resources=sorted(resources, key=lambda resource: resource.uri),
        metadata=metadata,
    )
    return redact_snapshot(snapshot) if redact else snapshot


def capture_mcp_sse(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    timeout: float = 15.0,
    server_name: str | None = None,
    redact: bool = True,
) -> InterfaceSnapshot:
    """Connect to a remote MCP server over SSE and capture tools/prompts/resources.

    Authentication headers (``Authorization``, ``X-Api-Key``, cookies, …) may be
    supplied for the HTTP requests but are **never** written into snapshot
    metadata — only non-secret header names and a redacted endpoint URL are kept.
    """
    request_headers = _filter_request_headers(headers)
    session = _SseSession(url, headers=request_headers, timeout=timeout)
    session.start()
    try:
        init = session.rpc(
            1,
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "tool-semantics", "version": "0.1.0"},
            },
        )
        session.notify("notifications/initialized")
        tools_result = session.rpc(2, "tools/list", {})
        prompts: list[PromptContract] = []
        resources: list[ResourceContract] = []
        try:
            prompts_result = session.rpc(3, "prompts/list", {})
            raw_prompts = (
                prompts_result.get("prompts", []) if isinstance(prompts_result, dict) else []
            )
            prompts = [_prompt_from_mcp(item) for item in raw_prompts if isinstance(item, dict)]
        except McpCaptureError:
            prompts = []
        try:
            resources_result = session.rpc(4, "resources/list", {})
            raw_resources = (
                resources_result.get("resources", []) if isinstance(resources_result, dict) else []
            )
            resources = [
                _resource_from_mcp(item) for item in raw_resources if isinstance(item, dict)
            ]
        except McpCaptureError:
            resources = []

        raw_tools = tools_result.get("tools", []) if isinstance(tools_result, dict) else []
        if not isinstance(raw_tools, list):
            raise McpCaptureError("tools/list result.tools must be an array")
        tools = [_tool_from_mcp(item) for item in raw_tools if isinstance(item, dict)]
        server_info = init.get("serverInfo", {}) if isinstance(init, dict) else {}
        resolved_name = (
            server_name
            or (server_info.get("name") if isinstance(server_info, dict) else None)
            or _safe_endpoint_for_metadata(url)
        )
        metadata = {
            "transport": "sse",
            "endpoint": _safe_endpoint_for_metadata(url),
            "request_header_names": _headers_for_metadata(request_headers),
        }
        return _snapshot_from_lists(
            protocol="mcp-sse",
            server_name=str(resolved_name),
            server_version=(
                str(server_info.get("version"))
                if isinstance(server_info, dict) and server_info.get("version") is not None
                else None
            ),
            tools=tools,
            prompts=prompts,
            resources=resources,
            metadata=metadata,
            redact=redact,
        )
    finally:
        session.close()


# Re-export for typing convenience in callers that inspect parameters.
__all__ = [
    "McpCaptureError",
    "capture_mcp_sse",
    "capture_mcp_stdio",
]
