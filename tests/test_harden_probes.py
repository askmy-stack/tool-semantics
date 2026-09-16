"""Tests for hardening model-backed probe payloads (#66)."""

from __future__ import annotations

import json

from tool_semantics.models import InterfaceSnapshot, RiskLevel, ToolContract, ToolParameter
from tool_semantics.probes import _tools_as_openai_schemas
from tool_semantics.runner import OpenAICompatibleRunner, RunnerConfig


def test_outbound_tool_schemas_omit_secret_parameter_names() -> None:
    snapshot = InterfaceSnapshot(
        server_name="demo",
        tools=[
            ToolContract(
                name="connect",
                description="Connect with credentials",
                parameters=[
                    ToolParameter(name="host", schema={"type": "string"}, required=True),
                    ToolParameter(
                        name="api_key",
                        schema={"type": "string", "default": "sk-live-secret"},
                        required=True,
                    ),
                    ToolParameter(
                        name="token",
                        schema={"type": "string"},
                        required=False,
                    ),
                ],
                risk=RiskLevel.EXTERNAL_WRITE,
            )
        ],
    )
    schemas = _tools_as_openai_schemas(snapshot)
    blob = json.dumps(schemas)
    assert "api_key" not in blob
    assert "sk-live-secret" not in blob
    assert "token" not in blob
    assert "host" in blob
    props = schemas[0]["function"]["parameters"]["properties"]
    assert "host" in props
    assert "api_key" not in props


def test_model_completion_raw_omitted_by_default_and_redacted_when_enabled() -> None:
    runner = OpenAICompatibleRunner(model="gpt-test", api_key="test-key", base_url="http://example")
    raw = {
        "choices": [{"message": {"content": "hi", "tool_calls": []}}],
        "authorization": "Bearer secret-token",
        "nested": {"api_key": "x"},
    }
    default = runner._parse(raw, RunnerConfig())
    assert default.raw == {}
    with_raw = runner._parse(raw, RunnerConfig(include_raw=True))
    assert with_raw.raw.get("authorization") == "***REDACTED***"
    assert with_raw.raw["nested"]["api_key"] == "***REDACTED***"
    assert "secret-token" not in json.dumps(with_raw.raw)
