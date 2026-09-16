"""Tests for optional LLM semantic judge (#81)."""

from __future__ import annotations

from tool_semantics.diff import Change, CompatibilityReport, Severity, compare_snapshots
from tool_semantics.judge import (
    JUDGE_LABEL,
    JudgeOutcome,
    JudgeReport,
    assert_judge_does_not_mutate_report,
    judge_does_not_clear_breaking,
    judge_tool_pair,
    merge_judge_into_markdown,
    render_judge_markdown,
)
from tool_semantics.models import InterfaceSnapshot, RiskLevel, ToolContract, ToolParameter
from tool_semantics.runner import FakeModelRunner, ModelCompletion, RunnerMetadata


def _tool(name: str, description: str, *, risk: RiskLevel = RiskLevel.READ_ONLY) -> ToolContract:
    return ToolContract(
        name=name,
        description=description,
        parameters=[ToolParameter(name="query", schema={"type": "string"}, required=True)],
        risk=risk,
    )


def _completion(text: str) -> ModelCompletion:
    return ModelCompletion(
        text=text,
        metadata=RunnerMetadata(provider="fake", model="fake-judge"),
    )


def test_judge_opt_in_labels_model_based() -> None:
    runner = FakeModelRunner(
        [
            _completion(
                '{"same_user_task": true, "confidence": 0.9, "rationale": "Both search issues."}'
            )
        ]
    )
    left = _tool("search_issues", "Search GitHub issues by query")
    right = _tool("find_issues", "Find GitHub issues matching a query")
    verdict = judge_tool_pair(left, right, runner)
    assert verdict.label == JUDGE_LABEL
    assert verdict.outcome == JudgeOutcome.SAME_TASK
    assert verdict.same_user_task is True
    assert verdict.confidence == 0.9
    md = render_judge_markdown(JudgeReport(verdicts=[verdict]))
    assert JUDGE_LABEL in md
    assert "same_task" in md


def test_judge_cannot_clear_deterministic_breaking() -> None:
    left = _tool("search_issues", "Search issues")
    right = _tool("find_work_items", "Retrieve work items")
    baseline = InterfaceSnapshot(server_name="v1", tools=[left])
    candidate = InterfaceSnapshot(server_name="v2", tools=[right])
    det = compare_snapshots(baseline, candidate)
    assert any(change.code == "tool.removed" for change in det.changes)
    before = list(det.changes)

    runner = FakeModelRunner(
        [
            _completion(
                '{"same_user_task": true, "confidence": 0.99, "rationale": "Obviously the same."}'
            )
        ]
    )
    det_with_subject = CompatibilityReport(
        baseline="v1",
        candidate="v2",
        changes=[
            Change(
                severity=Severity.BREAKING,
                code="tool.removed",
                subject="search_issues",
                message="removed",
            )
        ],
    )
    verdict = judge_tool_pair(
        left,
        right,
        runner,
        deterministic_report=det_with_subject,
    )
    assert verdict.blocked_by_deterministic is True
    assert verdict.same_user_task is False
    assert verdict.outcome == JudgeOutcome.DIFFERENT_TASK
    assert "Deterministic" in verdict.rationale

    judge_report = JudgeReport(verdicts=[verdict])
    assert judge_does_not_clear_breaking(det_with_subject, judge_report)
    assert assert_judge_does_not_mutate_report(before, det)
    combined = merge_judge_into_markdown("# Deterministic report\n", judge_report)
    assert JUDGE_LABEL in combined
    assert combined.index("Deterministic report") < combined.index(JUDGE_LABEL)


def test_unparseable_response() -> None:
    runner = FakeModelRunner([_completion("not json at all")])
    verdict = judge_tool_pair(_tool("a", "A"), _tool("b", "B"), runner)
    assert verdict.outcome == JudgeOutcome.UNPARSEABLE
