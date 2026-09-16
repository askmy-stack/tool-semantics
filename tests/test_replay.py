"""Tests for agent trace replay (#84)."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from tool_semantics.cli import app
from tool_semantics.models import InterfaceSnapshot, ToolContract, ToolParameter
from tool_semantics.replay import (
    ReplayEvidence,
    ReplayMode,
    ReplayStatus,
    replay_trace,
    replay_traces,
)
from tool_semantics.runner import FakeModelRunner, ModelCompletion, RunnerMetadata, ToolCallRequest
from tool_semantics.scanner import capture_manifest, write_snapshot
from tool_semantics.traces import load_trace

runner = CliRunner()


def _snapshot_with(*tools: ToolContract) -> InterfaceSnapshot:
    return InterfaceSnapshot(server_name="demo", server_version="cand", tools=list(tools))


def test_offline_replay_ok_against_matching_snapshot() -> None:
    snapshot = capture_manifest(Path("examples/github_server_v1.json"))
    trace = load_trace(Path("examples/traces/github_search_issues.json"))
    result = replay_trace(trace, snapshot, mode=ReplayMode.OFFLINE)
    assert result.status is ReplayStatus.OK
    assert result.steps[0].evidence is ReplayEvidence.DETERMINISTIC
    assert result.steps[0].tool_present is True
    assert result.steps[0].arguments_valid is True


def test_offline_replay_fails_when_tool_removed() -> None:
    snapshot = _snapshot_with(
        ToolContract(
            name="other_tool",
            description="unrelated",
            parameters=[ToolParameter(name="q", schema={"type": "string"}, required=True)],
        )
    )
    trace = load_trace(Path("examples/traces/github_search_issues.json"))
    result = replay_trace(trace, snapshot)
    assert result.status is ReplayStatus.FAILED
    assert "absent" in result.steps[0].message


def test_offline_replay_fails_when_required_arg_missing_from_schema_change() -> None:
    snapshot = _snapshot_with(
        ToolContract(
            name="search_issues",
            description="Search issues",
            parameters=[
                ToolParameter(name="query", schema={"type": "string"}, required=True),
                ToolParameter(name="state", schema={"type": "string"}, required=True),
                ToolParameter(name="author", schema={"type": "string"}, required=True),
            ],
        )
    )
    trace = load_trace(Path("examples/traces/github_search_issues.json"))
    result = replay_trace(trace, snapshot)
    assert result.status is ReplayStatus.FAILED
    assert result.steps[0].evidence is ReplayEvidence.DETERMINISTIC
    assert "Missing required" in result.steps[0].message


def test_batch_counts_and_cli(tmp_path: Path) -> None:
    snapshot = capture_manifest(Path("examples/github_server_v1.json"))
    snap_path = tmp_path / "cand.json"
    write_snapshot(snapshot, snap_path)

    ok_trace = load_trace(Path("examples/traces/github_search_issues.json"))
    # Multi-step includes create_issue_comment which is not on v1 → failed.
    multi = load_trace(Path("examples/traces/github_multi_step.json"))
    report = replay_traces([ok_trace, multi], snapshot)
    assert report.counts["ok"] == 1
    assert report.counts["failed"] == 1
    assert not report.passed

    result = runner.invoke(
        app,
        [
            "replay",
            "examples/traces/github_search_issues.json",
            str(snap_path),
            "--mode",
            "offline",
        ],
    )
    assert result.exit_code == 0
    assert "ok=" in result.output


def test_model_mode_reports_selection_drift() -> None:
    snapshot = capture_manifest(Path("examples/github_server_v1.json"))
    trace = load_trace(Path("examples/traces/github_search_issues.json"))
    fake = FakeModelRunner(
        [
            ModelCompletion(
                tool_calls=[ToolCallRequest(name="create_issue", arguments={})],
                metadata=RunnerMetadata(provider="fake", model="fake"),
            )
        ]
    )
    result = replay_trace(trace, snapshot, mode=ReplayMode.MODEL, runner=fake)
    assert result.status is ReplayStatus.CHANGED
    assert result.steps[0].evidence is ReplayEvidence.MODEL_BASED
    assert result.steps[0].reselected_tool == "create_issue"


def test_cli_batch_directory_exit_one_on_failure(tmp_path: Path) -> None:
    # Candidate without search_issues → fail.
    empty = _snapshot_with(
        ToolContract(name="noop", description="noop", parameters=[]),
    )
    snap_path = tmp_path / "empty.json"
    write_snapshot(empty, snap_path)
    result = runner.invoke(
        app,
        ["replay", "examples/traces", str(snap_path), "--mode", "offline"],
    )
    assert result.exit_code == 1


def test_validate_trace_still_used_for_bad_input(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text('{"intent": "x"}', encoding="utf-8")
    snap = tmp_path / "s.json"
    write_snapshot(_snapshot_with(), snap)
    result = runner.invoke(app, ["replay", str(bad), str(snap)])
    assert result.exit_code == 2
