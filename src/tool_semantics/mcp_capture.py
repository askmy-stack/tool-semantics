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

from tool_semantics import __version__
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

# Protocol generations we can initialize against for tools/list capture.
# See docs/mcp-versions.md.
SUPPORTED_PROTOCOL_VERSIONS = frozenset(
    {
        "2024-11-05",
        "2025-03-26",
        "2025-06-18",
        "2025-11-25",
    }
)
PREFERRED_PROTOCOL_LEGACY = "2024-11-05"
PREFERRED_PROTOCOL_HTTP = "2025-03-26"


class McpCaptureError(ManifestError):
    """Raised when a live MCP capture fails.

    Message prefix convention (for CLI/automation):
    ``[authentication]``, ``[network]``, ``[protocol]``, ``[unsupported]``,
    ``[invalid_response]``, ``[timeout]``, ``[unsupported_server]``.
    """


def _capture_error(kind: str, message: str) -> McpCaptureError:
    """Build a categorized capture error (see ``McpCaptureError`` prefixes)."""
    return McpCaptureError(f"[{kind}] {message}")


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


def _initialize_params(preferred_version: str) -> dict[str, Any]:
    return {
        "protocolVersion": preferred_version,
        "capabilities": {},
        "clientInfo": {"name": "tool-semantics", "version": __version__},
    }


def _negotiated_protocol_version(init: Any) -> str:
    if not isinstance(init, dict):
        raise McpCaptureError("initialize result must be an object")
    version = init.get("protocolVersion")
    if not isinstance(version, str) or not version:
        raise McpCaptureError("initialize result missing protocolVersion string")
    if version not in SUPPORTED_PROTOCOL_VERSIONS:
        supported = ", ".join(sorted(SUPPORTED_PROTOCOL_VERSIONS))
        raise _capture_error(
            "unsupported",
            f"Unsupported MCP protocol version {version!r}. "
            f"tool-semantics supports: {supported}. "
            "Upgrade tool-semantics or use a compatible MCP server.",
        )
    return version


def _server_capabilities(init: Any) -> dict[str, Any]:
    if not isinstance(init, dict):
        return {}
    caps = init.get("capabilities")
    return caps if isinstance(caps, dict) else {}


def _server_extensions_metadata(init: Any) -> dict[str, Any]:
    """Best-effort extensions advertised at initialize (#91)."""
    from tool_semantics.extensions import extensions_metadata

    return extensions_metadata(init)


def _list_interface_via_rpc(
    rpc: Any,
    notify: Any,
    *,
    preferred_protocol: str,
) -> tuple[Any, list[ToolContract], list[PromptContract], list[ResourceContract], str]:
    """Run initialize + list RPCs. ``rpc(id, method, params)`` / ``notify(method)``."""
    init = rpc(1, "initialize", _initialize_params(preferred_protocol))
    negotiated = _negotiated_protocol_version(init)
    notify("notifications/initialized")
    tools_result = rpc(2, "tools/list", {})
    prompts: list[PromptContract] = []
    resources: list[ResourceContract] = []
    try:
        prompts_result = rpc(3, "prompts/list", {})
        raw_prompts = prompts_result.get("prompts", []) if isinstance(prompts_result, dict) else []
        prompts = [_prompt_from_mcp(item) for item in raw_prompts if isinstance(item, dict)]
    except McpCaptureError:
        prompts = []
    try:
        resources_result = rpc(4, "resources/list", {})
        raw_resources = (
            resources_result.get("resources", []) if isinstance(resources_result, dict) else []
        )
        resources = [_resource_from_mcp(item) for item in raw_resources if isinstance(item, dict)]
    except McpCaptureError:
        resources = []

    raw_tools = tools_result.get("tools", []) if isinstance(tools_result, dict) else []
    if not isinstance(raw_tools, list):
        raise McpCaptureError("tools/list result.tools must be an array")
    tools = [_tool_from_mcp(item) for item in raw_tools if isinstance(item, dict)]
    return init, tools, prompts, resources, negotiated


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

        def rpc(request_id: int, method: str, params: dict[str, Any] | None = None) -> Any:
            return _rpc(
                process.stdin,
                process.stdout,
                request_id,
                method,
                params,
                timeout=timeout,
            )

        def notify(method: str, params: dict[str, Any] | None = None) -> None:
            message: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
            if params is not None:
                message["params"] = params
            _write_message(process.stdin, message)

        init, tools, prompts, resources, negotiated = _list_interface_via_rpc(
            rpc,
            notify,
            preferred_protocol=PREFERRED_PROTOCOL_LEGACY,
        )
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
            metadata={
                "transport": "stdio",
                "command": command,
                "protocol_version": negotiated,
                "server_capabilities": _server_capabilities(init),
                "extensions": _server_extensions_metadata(init),
            },
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


def _parse_sse_json_rpc_response(raw: bytes, request_id: int, method: str) -> Any:
    """Parse a Streamable HTTP SSE body for the JSON-RPC response matching ``request_id``."""
    text = raw.decode("utf-8", errors="replace")
    event_name = "message"
    data_lines: list[str] = []
    for line in text.splitlines():
        if line == "":
            if data_lines:
                data = "\n".join(data_lines)
                if event_name in {"message", ""}:
                    try:
                        payload = json.loads(data)
                    except json.JSONDecodeError:
                        payload = None
                    if isinstance(payload, dict) and payload.get("id") == request_id:
                        if "error" in payload:
                            raise McpCaptureError(f"MCP error for {method}: {payload['error']}")
                        return payload.get("result")
            event_name = "message"
            data_lines = []
            continue
        if line.startswith(":"):
            continue
        if line.startswith("event:"):
            event_name = line[6:].strip() or "message"
        elif line.startswith("data:"):
            data_lines.append(line[5:].lstrip())
    if data_lines:
        data = "\n".join(data_lines)
        try:
            payload = json.loads(data)
        except json.JSONDecodeError:
            payload = None
        if isinstance(payload, dict) and payload.get("id") == request_id:
            if "error" in payload:
                raise McpCaptureError(f"MCP error for {method}: {payload['error']}")
            return payload.get("result")
    raise McpCaptureError(f"Streamable HTTP SSE response missing JSON-RPC result for {method}")


class _StreamableHttpSession:
    """MCP Streamable HTTP client (POST JSON-RPC to a single MCP endpoint)."""

    def __init__(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        timeout: float = 15.0,
        preferred_protocol: str = PREFERRED_PROTOCOL_HTTP,
    ) -> None:
        if not url or not isinstance(url, str):
            raise McpCaptureError("Streamable HTTP URL must be a non-empty string")
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise McpCaptureError(f"Invalid Streamable HTTP endpoint URL: {url!r}")
        self._url = url
        self._headers = _filter_request_headers(headers)
        self._timeout = timeout
        self._preferred_protocol = preferred_protocol
        self._protocol_version: str | None = None
        self._session_id: str | None = None
        self._closed = False

    @property
    def protocol_version(self) -> str | None:
        return self._protocol_version

    @property
    def has_session(self) -> bool:
        return self._session_id is not None

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._session_id is None:
            return
        request = urllib.request.Request(
            self._url,
            headers=self._request_headers(include_protocol=True),
            method="DELETE",
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout):
                return
        except Exception:  # noqa: BLE001 — best-effort session teardown
            return

    def _request_headers(self, *, include_protocol: bool) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            **self._headers,
        }
        if include_protocol and self._protocol_version:
            headers["MCP-Protocol-Version"] = self._protocol_version
        if self._session_id:
            headers["Mcp-Session-Id"] = self._session_id
        return headers

    def _classify_http_error(self, exc: urllib.error.HTTPError, *, method: str) -> McpCaptureError:
        if exc.code in {401, 403}:
            return _capture_error(
                "authentication",
                f"Streamable HTTP authentication/HTTP error {exc.code} for {method}: {exc.reason}",
            )
        if exc.code == 400:
            body = ""
            try:
                body = exc.read().decode("utf-8", errors="replace")[:500]
            except Exception:  # noqa: BLE001
                body = ""
            detail = f" ({body})" if body else ""
            return _capture_error(
                "protocol",
                f"Streamable HTTP protocol/HTTP error 400 for {method}: {exc.reason}{detail}",
            )
        if exc.code == 404:
            return _capture_error(
                "unsupported_server",
                f"Streamable HTTP endpoint not found (HTTP 404) for {method}: {exc.reason}",
            )
        if exc.code == 405:
            return _capture_error(
                "unsupported_server",
                f"Streamable HTTP method not allowed (HTTP 405) for {method}: {exc.reason}",
            )
        return _capture_error(
            "protocol",
            f"Streamable HTTP request failed with HTTP {exc.code} for {method}: {exc.reason}",
        )

    def rpc(self, request_id: int, method: str, params: dict[str, Any] | None = None) -> Any:
        message: dict[str, Any] = {"jsonrpc": "2.0", "id": request_id, "method": method}
        if params is not None:
            message["params"] = params
        body = json.dumps(message, separators=(",", ":")).encode("utf-8")
        include_protocol = method != "initialize"
        request = urllib.request.Request(
            self._url,
            data=body,
            headers=self._request_headers(include_protocol=include_protocol),
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as response:
                if method == "initialize":
                    session_header = response.headers.get("Mcp-Session-Id")
                    if isinstance(session_header, str) and session_header.strip():
                        self._session_id = session_header.strip()
                content_type = (response.headers.get("Content-Type") or "").lower()
                raw = response.read()
                if "text/event-stream" in content_type:
                    result = _parse_sse_json_rpc_response(raw, request_id, method)
                else:
                    if not raw:
                        raise _capture_error(
                            "invalid_response",
                            f"Empty Streamable HTTP response for {method}",
                        )
                    try:
                        payload = json.loads(raw.decode("utf-8"))
                    except json.JSONDecodeError as exc:
                        raise _capture_error(
                            "invalid_response",
                            f"Invalid MCP JSON response for {method}: {exc}",
                        ) from exc
                    if not isinstance(payload, dict) or payload.get("id") != request_id:
                        raise _capture_error(
                            "invalid_response",
                            f"Unexpected MCP JSON-RPC response shape for {method}",
                        )
                    if "error" in payload:
                        raise McpCaptureError(f"MCP error for {method}: {payload['error']}")
                    result = payload.get("result")
                if method == "initialize":
                    self._protocol_version = _negotiated_protocol_version(result)
                return result
        except urllib.error.HTTPError as exc:
            raise self._classify_http_error(exc, method=method) from exc
        except TimeoutError as exc:
            raise _capture_error(
                "timeout",
                f"Timed out contacting Streamable HTTP endpoint "
                f"{_safe_endpoint_for_metadata(self._url)!r} during {method}",
            ) from exc
        except urllib.error.URLError as exc:
            reason = getattr(exc, "reason", exc)
            if isinstance(reason, TimeoutError) or "timed out" in str(reason).lower():
                raise _capture_error(
                    "timeout",
                    f"Timed out contacting Streamable HTTP endpoint "
                    f"{_safe_endpoint_for_metadata(self._url)!r} during {method}",
                ) from exc
            raise _capture_error(
                "network",
                f"Network failure contacting Streamable HTTP endpoint "
                f"{_safe_endpoint_for_metadata(self._url)!r}: {reason}",
            ) from exc

    def notify(self, method: str, params: dict[str, Any] | None = None) -> None:
        message: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            message["params"] = params
        body = json.dumps(message, separators=(",", ":")).encode("utf-8")
        request = urllib.request.Request(
            self._url,
            data=body,
            headers=self._request_headers(include_protocol=True),
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as response:
                # 202 Accepted is typical for notifications; ignore body.
                _ = response.status
                return
        except urllib.error.HTTPError as exc:
            if exc.code in {401, 403}:
                raise _capture_error(
                    "authentication",
                    f"Streamable HTTP authentication/HTTP error {exc.code} "
                    f"for notification {method}",
                ) from exc
            # Some servers return 200 with empty body for notifications.
            if exc.code >= 400:
                raise self._classify_http_error(exc, method=method) from exc
        except urllib.error.URLError as exc:
            raise _capture_error(
                "network",
                f"Network failure during Streamable HTTP notification {method}: {exc.reason}",
            ) from exc


def capture_mcp_sse(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    timeout: float = 15.0,
    server_name: str | None = None,
    redact: bool = True,
) -> InterfaceSnapshot:
    """Connect to a remote MCP server over legacy SSE and capture tools/prompts/resources.

    Authentication headers (``Authorization``, ``X-Api-Key``, cookies, …) may be
    supplied for the HTTP requests but are **never** written into snapshot
    metadata — only non-secret header names and a redacted endpoint URL are kept.
    """
    request_headers = _filter_request_headers(headers)
    session = _SseSession(url, headers=request_headers, timeout=timeout)
    session.start()
    try:
        init, tools, prompts, resources, negotiated = _list_interface_via_rpc(
            session.rpc,
            session.notify,
            preferred_protocol=PREFERRED_PROTOCOL_LEGACY,
        )
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
            "protocol_version": negotiated,
            "server_capabilities": _server_capabilities(init),
            "extensions": _server_extensions_metadata(init),
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


def capture_mcp_http(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    timeout: float = 15.0,
    server_name: str | None = None,
    redact: bool = True,
) -> InterfaceSnapshot:
    """Connect to a remote MCP server over Streamable HTTP and capture the interface.

    Auth headers may be supplied for requests but are never written into snapshot
    metadata. Negotiated ``protocolVersion`` and transport are recorded.
    """
    request_headers = _filter_request_headers(headers)
    session = _StreamableHttpSession(
        url,
        headers=request_headers,
        timeout=timeout,
        preferred_protocol=PREFERRED_PROTOCOL_HTTP,
    )
    try:
        init, tools, prompts, resources, negotiated = _list_interface_via_rpc(
            session.rpc,
            session.notify,
            preferred_protocol=PREFERRED_PROTOCOL_HTTP,
        )
        server_info = init.get("serverInfo", {}) if isinstance(init, dict) else {}
        resolved_name = (
            server_name
            or (server_info.get("name") if isinstance(server_info, dict) else None)
            or _safe_endpoint_for_metadata(url)
        )
        metadata = {
            "transport": "streamable-http",
            "endpoint": _safe_endpoint_for_metadata(url),
            "request_header_names": _headers_for_metadata(request_headers),
            "protocol_version": negotiated,
            "server_capabilities": _server_capabilities(init),
            "extensions": _server_extensions_metadata(init),
            "mcp_session": session.has_session,
        }
        return _snapshot_from_lists(
            protocol="mcp-http",
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


def _is_transport_mismatch_error(exc: McpCaptureError) -> bool:
    """Whether a Streamable HTTP failure should trigger legacy SSE fallback."""
    text = str(exc).lower()
    if "[authentication]" in text or "authentication/http error" in text:
        return False
    if "[unsupported]" in text or "unsupported mcp protocol version" in text:
        return False
    if "[network]" in text or "network failure" in text:
        return True
    if "[timeout]" in text or "timed out" in text:
        return True
    if "[unsupported_server]" in text or "http 404" in text or "http 405" in text:
        return True
    if "[protocol]" in text or "http 400" in text:
        return True
    if "[invalid_response]" in text or "invalid mcp json response" in text:
        return True
    if "empty streamable http response" in text or "unexpected mcp json-rpc" in text:
        return True
    return False


def capture_mcp_remote(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    timeout: float = 15.0,
    server_name: str | None = None,
    redact: bool = True,
) -> InterfaceSnapshot:
    """Auto-detect remote transport: Streamable HTTP first, then legacy SSE.

    Matches the MCP backwards-compatibility guidance for clients given a bare URL.
    Authentication failures and unsupported protocol versions do not fall back.
    """
    http_error: McpCaptureError | None = None
    try:
        return capture_mcp_http(
            url,
            headers=headers,
            timeout=timeout,
            server_name=server_name,
            redact=redact,
        )
    except McpCaptureError as exc:
        if not _is_transport_mismatch_error(exc):
            raise
        http_error = exc
    try:
        return capture_mcp_sse(
            url,
            headers=headers,
            timeout=timeout,
            server_name=server_name,
            redact=redact,
        )
    except McpCaptureError as sse_exc:
        raise _capture_error(
            "unsupported_server",
            f"Remote MCP capture failed for {_safe_endpoint_for_metadata(url)!r}. "
            f"Streamable HTTP: {http_error}. Legacy SSE: {sse_exc}",
        ) from sse_exc


# Re-export for typing convenience in callers that inspect parameters.
__all__ = [
    "McpCaptureError",
    "PREFERRED_PROTOCOL_HTTP",
    "PREFERRED_PROTOCOL_LEGACY",
    "SUPPORTED_PROTOCOL_VERSIONS",
    "capture_mcp_http",
    "capture_mcp_remote",
    "capture_mcp_sse",
    "capture_mcp_stdio",
]
