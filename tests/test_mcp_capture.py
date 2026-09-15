from pathlib import Path

import pytest
from fixtures.fake_mcp_sse_server import FakeMcpSseServer

from tool_semantics.mcp_capture import McpCaptureError, capture_mcp_sse, capture_mcp_stdio
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
