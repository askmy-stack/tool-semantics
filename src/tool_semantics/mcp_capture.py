from __future__ import annotations

import json
import os
import select
import subprocess
import time
from pathlib import Path
from typing import Any

from tool_semantics.models import (
    InterfaceSnapshot,
    PromptContract,
    ResourceContract,
    RiskLevel,
    ToolContract,
)
from tool_semantics.redact import redact_snapshot
from tool_semantics.scanner import ManifestError, _normalize_parameters


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


def capture_mcp_sse(url: str, **_: Any) -> InterfaceSnapshot:
    """SSE transport placeholder — stdio is the supported live capture path today."""
    raise McpCaptureError(
        f"SSE capture is not implemented yet (requested url={url!r}). "
        "Use stdio capture: tool-semantics capture-mcp -- <command>."
    )


# Re-export for typing convenience in callers that inspect parameters.
__all__ = [
    "McpCaptureError",
    "capture_mcp_sse",
    "capture_mcp_stdio",
]
