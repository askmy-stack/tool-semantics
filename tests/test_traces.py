"""Tests for versioned agent trace schema (#83)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tool_semantics.traces import (
    TRACE_VERSION,
    TraceValidationError,
    load_trace,
    load_traces,
    redact_trace,
    trace_json_schema,
    validate_trace,
    write_trace,
)


def test_accept_single_step_example() -> None:
    trace = load_trace(Path("examples/traces/github_search_issues.json"))
    assert trace.tool_semantics_trace_version == TRACE_VERSION
    assert trace.intent
    assert trace.selected_tool == "search_issues"
    assert "query" in trace.arguments
    steps = trace.effective_steps()
    assert len(steps) == 1
    assert steps[0].selected_tool == "search_issues"


def test_accept_multi_step_example() -> None:
    trace = load_trace(Path("examples/traces/github_multi_step.json"))
    assert len(trace.turns) == 2
    assert trace.selected_tool is None
    assert trace.effective_steps()[1].selected_tool == "create_issue_comment"


def test_reject_missing_selected_tool_and_turns() -> None:
    with pytest.raises(TraceValidationError, match="selected_tool") as exc_info:
        validate_trace(
            {
                "tool_semantics_trace_version": "1.0",
                "intent": "do something",
                "arguments": {},
            }
        )
    assert "turns" in str(exc_info.value)


def test_reject_missing_intent() -> None:
    with pytest.raises(TraceValidationError, match="intent"):
        validate_trace(
            {
                "tool_semantics_trace_version": "1.0",
                "selected_tool": "search_issues",
                "arguments": {"query": "x"},
            }
        )


def test_reject_unknown_version() -> None:
    with pytest.raises(TraceValidationError):
        validate_trace(
            {
                "tool_semantics_trace_version": "9.9",
                "intent": "x",
                "selected_tool": "search_issues",
                "arguments": {},
            }
        )


def test_reject_empty_turn_tool() -> None:
    with pytest.raises(TraceValidationError):
        validate_trace(
            {
                "tool_semantics_trace_version": "1.0",
                "intent": "workflow",
                "turns": [{"selected_tool": "", "arguments": {}}],
            }
        )


def test_redact_secret_arguments() -> None:
    trace = load_trace(Path("examples/traces/github_multi_step.json"))
    redacted = redact_trace(trace)
    assert redacted.turns[1].arguments["api_token"] == "***REDACTED***"
    assert redacted.turns[1].arguments["body"].startswith("Thanks")


def test_load_traces_directory_and_write(tmp_path: Path) -> None:
    traces = load_traces(Path("examples/traces"))
    assert len(traces) >= 2
    out = tmp_path / "out.json"
    write_trace(traces[0], out)
    round_trip = load_trace(out)
    assert round_trip.intent == traces[0].intent


def test_load_traces_array(tmp_path: Path) -> None:
    payload = [
        {
            "tool_semantics_trace_version": "1.0",
            "intent": "a",
            "selected_tool": "t1",
            "arguments": {},
        },
        {
            "tool_semantics_trace_version": "1.0",
            "intent": "b",
            "selected_tool": "t2",
            "arguments": {"x": 1},
        },
    ]
    path = tmp_path / "batch.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    traces = load_traces(path)
    assert [item.selected_tool for item in traces] == ["t1", "t2"]


def test_json_schema_exposes_version_and_required() -> None:
    schema = trace_json_schema()
    assert schema["title"] == "AgentTrace"
    props = schema["properties"]
    assert "tool_semantics_trace_version" in props
    assert "intent" in props
    assert "selected_tool" in props
    assert "arguments" in props
    assert "turns" in props


def test_missing_file_is_actionable() -> None:
    with pytest.raises(TraceValidationError, match="not found"):
        load_trace(Path("/tmp/does-not-exist-trace-83.json"))
