from pathlib import Path

import pytest
from fixtures.fake_mcp_http_server import FakeMcpHttpServer
from fixtures.fake_mcp_sse_server import FakeMcpSseServer

from tool_semantics.mcp_capture import (
    McpCaptureError,
    capture_mcp_http,
    capture_mcp_remote,
    capture_mcp_sse,
    capture_mcp_stdio,
)
from tool_semantics.redact import redact_mapping

FIXTURE = Path(__file__).parent / "fixtures" / "fake_mcp_server.py"


def test_capture_mcp_stdio_lists_tools_prompts_resources() -> None:
    snapshot = capture_mcp_stdio(["python", str(FIXTURE)])
    assert snapshot.protocol == "mcp-stdio"
    assert snapshot.server_name == "fake-mcp"
    assert snapshot.server_version == "1.2.3"
    assert [tool.name for tool in snapshot.tools] == ["echo"]
    assert snapshot.tools[0].output_schema is not None
    assert [prompt.name for prompt in snapshot.prompts] == ["summarize"]
    assert [resource.uri for resource in snapshot.resources] == ["memo://secret-token"]
    # api_key schema key is redacted in nested structures when key matches pattern —
    # parameter name itself is preserved; metadata secrets are redacted.
    assert snapshot.metadata["transport"] == "stdio"
    assert snapshot.metadata["protocol_version"] == "2024-11-05"


def test_redact_mapping_masks_secret_keys() -> None:
    payload = {"api_key": "abc", "nested": {"token": "xyz"}, "safe": "ok"}
    redacted = redact_mapping(payload)
    assert redacted["api_key"] == "***REDACTED***"
    assert redacted["nested"]["token"] == "***REDACTED***"
    assert redacted["safe"] == "ok"


def test_capture_mcp_sse_success() -> None:
    server = FakeMcpSseServer()
    server.start()
    try:
        snapshot = capture_mcp_sse(server.sse_url, timeout=5.0)
    finally:
        server.stop()
    assert snapshot.protocol == "mcp-sse"
    assert snapshot.server_name == "fake-sse-mcp"
    assert snapshot.server_version == "9.9.9"
    assert [tool.name for tool in snapshot.tools] == ["echo"]
    assert snapshot.metadata["transport"] == "sse"
    assert snapshot.metadata["protocol_version"] == "2024-11-05"
    assert "Authorization" not in str(snapshot.metadata)
    assert snapshot.metadata["endpoint"].startswith("http://127.0.0.1:")


def test_capture_mcp_sse_invalid_endpoint() -> None:
    with pytest.raises(McpCaptureError, match="Invalid SSE endpoint URL"):
        capture_mcp_sse("not-a-url")


def test_capture_mcp_sse_auth_error() -> None:
    server = FakeMcpSseServer(require_auth=True)
    server.start()
    try:
        with pytest.raises(McpCaptureError, match="authentication/HTTP error 401"):
            capture_mcp_sse(server.sse_url, timeout=5.0)
        snapshot = capture_mcp_sse(
            server.sse_url,
            headers={"Authorization": "Bearer secret-token"},
            timeout=5.0,
        )
    finally:
        server.stop()
    assert snapshot.server_name == "fake-sse-mcp"
    # Auth header values must never appear in metadata.
    assert "secret-token" not in str(snapshot.model_dump())
    assert snapshot.metadata.get("request_header_names") == []


def test_capture_mcp_http_success() -> None:
    server = FakeMcpHttpServer()
    server.start()
    try:
        snapshot = capture_mcp_http(server.mcp_url, timeout=5.0)
    finally:
        server.stop()
    assert snapshot.protocol == "mcp-http"
    assert snapshot.server_name == "fake-http-mcp"
    assert snapshot.server_version == "2.0.0"
    assert [tool.name for tool in snapshot.tools] == ["echo"]
    assert [prompt.name for prompt in snapshot.prompts] == ["greet"]
    assert [resource.uri for resource in snapshot.resources] == ["memo://notes"]
    assert snapshot.metadata["transport"] == "streamable-http"
    assert snapshot.metadata["protocol_version"] == "2025-03-26"
    assert snapshot.metadata["mcp_session"] is True
    assert "tools" in snapshot.metadata["server_capabilities"]


def test_capture_mcp_http_sse_response_body() -> None:
    server = FakeMcpHttpServer(respond_sse=True)
    server.start()
    try:
        snapshot = capture_mcp_http(server.mcp_url, timeout=5.0)
    finally:
        server.stop()
    assert snapshot.protocol == "mcp-http"
    assert [tool.name for tool in snapshot.tools] == ["echo"]


def test_capture_mcp_http_invalid_endpoint() -> None:
    with pytest.raises(McpCaptureError, match="Invalid Streamable HTTP endpoint URL"):
        capture_mcp_http("not-a-url")


def test_capture_mcp_http_auth_error() -> None:
    server = FakeMcpHttpServer(require_auth=True)
    server.start()
    try:
        with pytest.raises(McpCaptureError, match=r"\[authentication\].*401"):
            capture_mcp_http(server.mcp_url, timeout=5.0)
        snapshot = capture_mcp_http(
            server.mcp_url,
            headers={"Authorization": "Bearer secret-token"},
            timeout=5.0,
        )
    finally:
        server.stop()
    assert snapshot.server_name == "fake-http-mcp"
    assert "secret-token" not in str(snapshot.model_dump())
    assert snapshot.metadata.get("request_header_names") == []


def test_capture_mcp_http_unsupported_protocol_version() -> None:
    server = FakeMcpHttpServer(protocol_version="2099-01-01")
    server.start()
    try:
        with pytest.raises(McpCaptureError, match=r"\[unsupported\].*Unsupported MCP protocol"):
            capture_mcp_http(server.mcp_url, timeout=5.0)
    finally:
        server.stop()


def test_capture_mcp_remote_prefers_streamable_http() -> None:
    server = FakeMcpHttpServer()
    server.start()
    try:
        snapshot = capture_mcp_remote(server.mcp_url, timeout=5.0)
    finally:
        server.stop()
    assert snapshot.protocol == "mcp-http"
    assert snapshot.metadata["transport"] == "streamable-http"


def test_capture_mcp_remote_falls_back_to_sse() -> None:
    server = FakeMcpSseServer()
    server.start()
    try:
        snapshot = capture_mcp_remote(server.sse_url, timeout=5.0)
    finally:
        server.stop()
    assert snapshot.protocol == "mcp-sse"
    assert snapshot.metadata["transport"] == "sse"


def test_capture_mcp_remote_auth_does_not_fallback() -> None:
    server = FakeMcpHttpServer(require_auth=True)
    server.start()
    try:
        with pytest.raises(McpCaptureError, match=r"\[authentication\]"):
            capture_mcp_remote(server.mcp_url, timeout=5.0)
    finally:
        server.stop()


def test_capture_mcp_remote_total_failure() -> None:
    with pytest.raises(McpCaptureError, match=r"\[unsupported_server\].*Remote MCP capture failed"):
        capture_mcp_remote("http://127.0.0.1:9/no-mcp-here", timeout=1.0)


def test_capture_mcp_sse_timeout_waiting_for_endpoint() -> None:
    server = FakeMcpSseServer(hang_without_endpoint=True)
    server.start()
    try:
        with pytest.raises(McpCaptureError, match="[Tt]imeout|endpoint"):
            capture_mcp_sse(server.sse_url, timeout=0.3)
    finally:
        server.stop()


def test_capture_mcp_sse_empty_endpoint_event() -> None:
    server = FakeMcpSseServer(empty_endpoint=True)
    server.start()
    try:
        with pytest.raises(McpCaptureError, match="empty URL|endpoint"):
            capture_mcp_sse(server.sse_url, timeout=2.0)
    finally:
        server.stop()


def test_capture_mcp_sse_post_auth_failure() -> None:
    server = FakeMcpSseServer(post_fail_auth=True)
    server.start()
    try:
        with pytest.raises(McpCaptureError, match="POST failed with HTTP 401"):
            capture_mcp_sse(server.sse_url, timeout=5.0)
    finally:
        server.stop()


def test_capture_mcp_sse_notification_auth_failure() -> None:
    server = FakeMcpSseServer(notify_fail_auth=True)
    server.start()
    try:
        with pytest.raises(
            McpCaptureError,
            match="notification.*401|authentication/HTTP error 401",
        ):
            capture_mcp_sse(server.sse_url, timeout=5.0)
    finally:
        server.stop()
