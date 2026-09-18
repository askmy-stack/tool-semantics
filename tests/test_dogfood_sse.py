"""Optional live dogfood capture against a real MCP SSE server (#65).

Skipped in default PR CI when credentials are absent. Capture-only — never
executes discovered tools. Tokens come from env / CI secrets and must not appear
in snapshot JSON.
"""

from __future__ import annotations

import json
import os
import re

import pytest

from tool_semantics.mcp_capture import capture_mcp_sse

pytestmark = pytest.mark.integration

_URL_ENV = "TOOL_SEMANTICS_DOGFOOD_SSE_URL"
_TOKEN_ENV = "TOOL_SEMANTICS_DOGFOOD_SSE_TOKEN"
# Also accept the market-pulse names documented in docs/downstream.md
_URL_ENV_ALIASES = ("MARKET_PULSE_SSE_URL",)
_TOKEN_ENV_ALIASES = ("MARKET_PULSE_SSE_TOKEN", "TOKEN")


def _env_first(*names: str) -> str | None:
    for name in names:
        value = os.environ.get(name)
        if value:
            return value
    return None


def _require_dogfood_creds() -> tuple[str, str | None]:
    url = _env_first(_URL_ENV, *_URL_ENV_ALIASES)
    token = _env_first(_TOKEN_ENV, *_TOKEN_ENV_ALIASES)
    if not url:
        pytest.skip(f"Set {_URL_ENV} (or MARKET_PULSE_SSE_URL) to run live SSE dogfood capture")
    return url, token


def _assert_no_secrets_in_snapshot(payload: dict[str, object], token: str | None) -> None:
    dumped = json.dumps(payload, default=str)
    if token:
        assert token not in dumped
        # Common Bearer forms
        assert f"Bearer {token}" not in dumped
    # Auth header values must never be persisted; only header *names* are OK.
    assert not re.search(r'"authorization"\s*:\s*"Bearer ', dumped, re.IGNORECASE)


def test_live_dogfood_sse_capture_only() -> None:
    """Capture tools from a live SSE MCP server; never call tools/call."""
    url, token = _require_dogfood_creds()
    headers: dict[str, str] = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    snapshot = capture_mcp_sse(url, headers=headers or None, timeout=30.0, redact=True)

    assert snapshot.protocol == "mcp-sse"
    assert snapshot.metadata.get("transport") == "sse"
    assert len(snapshot.tools) > 0

    payload = json.loads(snapshot.model_dump_json(by_alias=True))
    _assert_no_secrets_in_snapshot(payload, token)

    # Capture path only lists interface — ensure we did not invent tool results.
    assert "tool_results" not in payload
    assert snapshot.metadata.get("request_header_names") is not None
    header_names = snapshot.metadata.get("request_header_names")
    if token and isinstance(header_names, list):
        assert any(str(name).lower() == "authorization" for name in header_names)
