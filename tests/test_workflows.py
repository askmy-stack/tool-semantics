"""Tests for stateful multi-step workflow evaluation (#108)."""

from __future__ import annotations

from tool_semantics.workflows import (
    WorkflowCheckpoint,
    WorkflowStep,
    WorkflowTask,
    WorkflowTrace,
    evaluate_workflow,
    evaluate_workflows,
    render_workflow_report_markdown,
)


def _triage_task() -> WorkflowTask:
    return WorkflowTask(
        id="triage-bug",
        intent="Find a bug issue and leave a triage comment",
        initial_state={"issue": None, "commented": False},
        final_state={"issue": {"number": 42, "state": "open"}, "commented": True},
        checkpoints=[
            WorkflowCheckpoint(
                id="found-issue",
                required_tools=["search_issues"],
                state_contains={"issue": {"number": 42}},
            ),
            WorkflowCheckpoint(
                id="commented",
                required_tools=["search_issues", "create_comment"],
                state_contains={"commented": True},
            ),
        ],
        allowed_trajectories=[
            ["search_issues", "create_comment"],
            ["list_issues", "get_issue", "create_comment"],
        ],
    )


def test_alternate_trajectory_passes_on_final_state() -> None:
    task = _triage_task()
    # Alternate path not identical to first allowed trajectory, but reaches final state.
    trace = WorkflowTrace(
        task_id="triage-bug",
        steps=[
            WorkflowStep(
                tool="list_issues",
                state_patch={"issue": {"number": 42, "state": "open"}},
            ),
            WorkflowStep(tool="get_issue", state_patch={}),
            WorkflowStep(tool="create_comment", state_patch={"commented": True}),
        ],
    )
    result = evaluate_workflow(task, trace)
    assert result.final_state_matched
    assert result.task_success
    assert result.passed
    assert result.trajectory_valid  # listed as second allowed path
    assert "Final state matched" in result.message


def test_unlisted_trajectory_still_passes_when_final_state_ok() -> None:
    task = _triage_task()
    trace = WorkflowTrace(
        task_id="triage-bug",
        steps=[
            WorkflowStep(
                tool="search_issues",
                state_patch={"issue": {"number": 42, "state": "open"}},
            ),
            WorkflowStep(tool="create_issue"),  # detour
            WorkflowStep(tool="create_comment", state_patch={"commented": True}),
        ],
    )
    result = evaluate_workflow(task, trace)
    assert result.passed
    assert result.final_state_matched
    assert not result.trajectory_valid or "alternate" in result.message.lower()
    assert "alternate trajectory" in result.message


def test_final_state_mismatch_fails_even_with_valid_tools() -> None:
    task = _triage_task()
    trace = WorkflowTrace(
        task_id="triage-bug",
        steps=[
            WorkflowStep(
                tool="search_issues",
                state_patch={"issue": {"number": 42, "state": "open"}},
            ),
            WorkflowStep(tool="create_comment"),  # forgot state_patch → commented stays False
        ],
    )
    result = evaluate_workflow(task, trace)
    assert not result.passed
    assert not result.final_state_matched


def test_dead_end_and_recovery_recorded() -> None:
    task = _triage_task()
    trace = WorkflowTrace(
        task_id="triage-bug",
        steps=[
            WorkflowStep(tool="search_issues", dead_end=True, note="empty results"),
            WorkflowStep(
                tool="search_issues",
                recovered=True,
                state_patch={"issue": {"number": 42, "state": "open"}},
            ),
            WorkflowStep(tool="create_comment", state_patch={"commented": True}),
        ],
    )
    result = evaluate_workflow(task, trace)
    assert result.passed
    assert result.dead_end_count == 1
    assert result.recovery_count == 1
    assert "Dead ends" in result.message
    assert "Recoveries" in result.message


def test_batch_rates_and_markdown() -> None:
    task = _triage_task()
    ok = WorkflowTrace(
        task_id="triage-bug",
        steps=[
            WorkflowStep(
                tool="search_issues",
                state_patch={"issue": {"number": 42, "state": "open"}},
            ),
            WorkflowStep(tool="create_comment", state_patch={"commented": True}),
        ],
    )
    bad = WorkflowTrace(task_id="triage-bug", steps=[WorkflowStep(tool="search_issues")])
    report = evaluate_workflows([task], [ok, bad])
    assert report.rates.task_level == 0.5
    assert report.rates.tool_level is not None
    assert report.rates.trajectory_level is not None
    md = render_workflow_report_markdown(report)
    assert "task-level (final state)" in md
    assert "tool-level" in md
    assert "trajectory-level" in md
