from pathlib import Path

import pytest

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


def test_capture_mcp_sse_not_implemented() -> None:
    with pytest.raises(McpCaptureError, match="SSE capture is not implemented"):
        capture_mcp_sse("https://example.com/sse")
