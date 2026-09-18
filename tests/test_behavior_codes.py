"""Tests for behavior.* change codes (#61)."""

from __future__ import annotations

from tool_semantics.behavior_codes import (
    BEHAVIOR_ARGUMENTS_INVALID,
    BEHAVIOR_DETERMINISTIC_FAILURE,
    BEHAVIOR_MISSING_DATA,
    BEHAVIOR_TOOL_SELECTION_FAILED,
    BEHAVIOR_UNSTABLE_PROBE,
    changes_from_model_probe_report,
    changes_from_stability_report,
    merge_behavior_changes,
)
from tool_semantics.diff import Change, CompatibilityReport, Severity
from tool_semantics.models import InterfaceSnapshot, RiskLevel, ToolContract, ToolParameter
from tool_semantics.probes import (
    ModelProbeOutcome,
    ModelProbeReport,
    ModelProbeResult,
    Probe,
    run_probe_trials,
)
from tool_semantics.runner import FakeModelRunner, ModelCompletion, RunnerMetadata, ToolCallRequest


def _snapshot() -> InterfaceSnapshot:
    return InterfaceSnapshot(
        server_name="demo",
        tools=[
            ToolContract(
                name="search_issues",
                description="Search",
                parameters=[ToolParameter(name="query", schema={"type": "string"}, required=True)],
                risk=RiskLevel.READ_ONLY,
            ),
            ToolContract(
                name="create_issue",
                description="Create",
                parameters=[ToolParameter(name="title", schema={"type": "string"}, required=True)],
                risk=RiskLevel.EXTERNAL_WRITE,
            ),
        ],
    )


def test_model_selection_and_args_emit_breaking_codes() -> None:
    report = ModelProbeReport(
        results=[
            ModelProbeResult(
                probe_id="bad-select",
                passed=False,
                message="wrong",
                selected_tool="create_issue",
                arguments={"title": "x"},
                outcome=ModelProbeOutcome.OK,
                tool_selection_correct=False,
                arguments_valid=True,
            ),
            ModelProbeResult(
                probe_id="bad-args",
                passed=False,
                message="args",
                selected_tool="search_issues",
                arguments={},
                outcome=ModelProbeOutcome.OK,
                tool_selection_correct=True,
                arguments_valid=False,
            ),
        ]
    )
    changes = changes_from_model_probe_report(report)
    codes = {change.code for change in changes}
    assert BEHAVIOR_TOOL_SELECTION_FAILED in codes
    assert BEHAVIOR_ARGUMENTS_INVALID in codes
    assert all(change.severity == Severity.BREAKING for change in changes)


def test_missing_data_is_info_not_breaking() -> None:
    report = ModelProbeReport(
        results=[
            ModelProbeResult(
                probe_id="empty",
                passed=False,
                message="no call",
                outcome=ModelProbeOutcome.MISSING_DATA,
                tool_selection_correct=False,
            )
        ]
    )
    changes = changes_from_model_probe_report(report)
    assert len(changes) == 1
    assert changes[0].code == BEHAVIOR_MISSING_DATA
    assert changes[0].severity == Severity.INFO


def test_skipped_emits_nothing() -> None:
    report = ModelProbeReport(
        results=[
            ModelProbeResult(
                probe_id="skip",
                passed=False,
                message="unapproved",
                outcome=ModelProbeOutcome.SKIPPED,
            )
        ]
    )
    assert changes_from_model_probe_report(report) == []


def test_stability_unstable_vs_deterministic_codes() -> None:
    snap = _snapshot()
    unstable_runner = FakeModelRunner(
        [
            ModelCompletion(
                tool_calls=[ToolCallRequest(name="search_issues", arguments={"query": "a"})],
                metadata=RunnerMetadata(provider="fake", model="m"),
            ),
            ModelCompletion(
                tool_calls=[ToolCallRequest(name="create_issue", arguments={"title": "x"})],
                metadata=RunnerMetadata(provider="fake", model="m"),
            ),
        ]
    )
    unstable = run_probe_trials(
        snap,
        [
            Probe(
                id="u",
                intent="search",
                expected_tool="search_issues",
                required_params=["query"],
                approved=True,
            )
        ],
        unstable_runner,
        trial_count=2,
    )
    unstable_changes = changes_from_stability_report(unstable)
    assert any(change.code == BEHAVIOR_UNSTABLE_PROBE for change in unstable_changes)
    assert all(change.severity == Severity.WARNING for change in unstable_changes)

    fail_runner = FakeModelRunner(
        [
            ModelCompletion(
                tool_calls=[ToolCallRequest(name="create_issue", arguments={"title": "x"})],
                metadata=RunnerMetadata(provider="fake", model="m"),
            )
            for _ in range(2)
        ]
    )
    failed = run_probe_trials(
        snap,
        [Probe(id="d", intent="search", expected_tool="search_issues", approved=True)],
        fail_runner,
        trial_count=2,
    )
    det = changes_from_stability_report(failed)
    assert any(change.code == BEHAVIOR_DETERMINISTIC_FAILURE for change in det)
    assert det[0].severity == Severity.BREAKING


def test_merge_behavior_changes_affects_compatibility() -> None:
    structural = CompatibilityReport(baseline="a", candidate="b", changes=[])
    assert structural.is_compatible
    merged = merge_behavior_changes(
        structural,
        [
            Change(
                severity=Severity.BREAKING,
                code=BEHAVIOR_TOOL_SELECTION_FAILED,
                subject="p",
                message="fail",
            )
        ],
    )
    assert not merged.is_compatible
    assert len(merged.changes) == 1
