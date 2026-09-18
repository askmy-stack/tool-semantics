"""Stateful multi-step workflow evaluation (#108).

Final expected state is the strongest success criterion: different valid
trajectories can pass when the resulting state matches. Intermediate
checkpoints are soft diagnostics. Fixture-based by default — no live MCP
tool execution.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from pydantic import BaseModel, Field


class WorkflowCheckpoint(BaseModel):
    """Optional intermediate expectation along a workflow."""

    id: str
    description: str = ""
    required_tools: list[str] = Field(default_factory=list)
    state_contains: dict[str, Any] = Field(default_factory=dict)


class WorkflowTask(BaseModel):
    """A multi-step task with checkpoints and a required final state."""

    id: str
    intent: str
    final_state: dict[str, Any]
    checkpoints: list[WorkflowCheckpoint] = Field(default_factory=list)
    # If non-empty, at least one listed tool sequence is a known-valid path.
    # Final-state match still wins even when the trajectory is absent here.
    allowed_trajectories: list[list[str]] = Field(default_factory=list)
    initial_state: dict[str, Any] = Field(default_factory=dict)


class WorkflowStep(BaseModel):
    """One recorded/simulated tool call in a workflow trace."""

    tool: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    # Declarative state update applied after the step (fixture harness).
    state_patch: dict[str, Any] = Field(default_factory=dict)
    dead_end: bool = False
    recovered: bool = False
    note: str | None = None


class WorkflowTrace(BaseModel):
    """Recorded trajectory for a workflow task (fixture or capture)."""

    task_id: str
    steps: list[WorkflowStep] = Field(default_factory=list)
    # Optional explicit final state; otherwise derived from patches.
    final_state: dict[str, Any] | None = None


class CheckpointOutcome(BaseModel):
    checkpoint_id: str
    passed: bool
    message: str


class WorkflowLevelRates(BaseModel):
    tool_level: float | None = None
    trajectory_level: float | None = None
    task_level: float | None = None


class WorkflowResult(BaseModel):
    task_id: str
    passed: bool
    task_success: bool
    trajectory_valid: bool
    tool_level_score: float
    final_state_matched: bool
    derived_final_state: dict[str, Any] = Field(default_factory=dict)
    checkpoint_outcomes: list[CheckpointOutcome] = Field(default_factory=list)
    dead_end_count: int = 0
    recovery_count: int = 0
    tools_called: list[str] = Field(default_factory=list)
    message: str = ""


class WorkflowReport(BaseModel):
    results: list[WorkflowResult] = Field(default_factory=list)
    rates: WorkflowLevelRates = Field(default_factory=WorkflowLevelRates)

    @property
    def passed(self) -> bool:
        return all(item.passed for item in self.results)


def _deep_update(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(base)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_update(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result


def _state_contains(actual: dict[str, Any], expected: dict[str, Any]) -> bool:
    """True when ``expected`` is a subset of ``actual`` (nested dicts allowed)."""
    for key, value in expected.items():
        if key not in actual:
            return False
        current = actual[key]
        if isinstance(value, dict):
            if not isinstance(current, dict) or not _state_contains(current, value):
                return False
        elif current != value:
            return False
    return True


def derive_final_state(task: WorkflowTask, trace: WorkflowTrace) -> dict[str, Any]:
    if trace.final_state is not None:
        return deepcopy(trace.final_state)
    state = deepcopy(task.initial_state)
    for step in trace.steps:
        if step.state_patch:
            state = _deep_update(state, step.state_patch)
    return state


def _trajectory_matches_allowed(tools: list[str], allowed: list[list[str]]) -> bool:
    if not allowed:
        return False
    return any(tools == path for path in allowed)


def _tool_level_score(task: WorkflowTask, tools_called: list[str]) -> float:
    """Fraction of checkpoint-required tools that appear somewhere in the trace."""
    required: list[str] = []
    for checkpoint in task.checkpoints:
        required.extend(checkpoint.required_tools)
    if not required:
        if not task.allowed_trajectories:
            return 1.0
        best = 0.0
        called = set(tools_called)
        for path in task.allowed_trajectories:
            if not path:
                continue
            best = max(best, len(called & set(path)) / len(set(path)))
        return round(best, 4)
    hits = sum(1 for name in required if name in tools_called)
    return round(hits / len(required), 4)


def evaluate_workflow(task: WorkflowTask, trace: WorkflowTrace) -> WorkflowResult:
    """Evaluate one workflow trace against a task definition."""
    if trace.task_id != task.id:
        return WorkflowResult(
            task_id=task.id,
            passed=False,
            task_success=False,
            trajectory_valid=False,
            tool_level_score=0.0,
            final_state_matched=False,
            message=f"Trace task_id '{trace.task_id}' does not match task '{task.id}'.",
        )

    tools_called = [step.tool for step in trace.steps]
    dead_ends = sum(1 for step in trace.steps if step.dead_end)
    recoveries = sum(1 for step in trace.steps if step.recovered)
    final_state = derive_final_state(task, trace)
    final_ok = _state_contains(final_state, task.final_state)

    checkpoints: list[CheckpointOutcome] = []
    seen: list[str] = []
    state = deepcopy(task.initial_state)
    step_index = 0
    for checkpoint in task.checkpoints:
        while step_index < len(trace.steps):
            step = trace.steps[step_index]
            seen.append(step.tool)
            if step.state_patch:
                state = _deep_update(state, step.state_patch)
            step_index += 1
            if all(name in seen for name in checkpoint.required_tools):
                state_ready = not checkpoint.state_contains or _state_contains(
                    state, checkpoint.state_contains
                )
                if state_ready:
                    break
        missing = [name for name in checkpoint.required_tools if name not in seen]
        state_ok = (
            _state_contains(state, checkpoint.state_contains) if checkpoint.state_contains else True
        )
        passed_cp = not missing and state_ok
        if missing:
            message = f"Missing tools before checkpoint: {', '.join(missing)}"
        elif not state_ok:
            message = "Checkpoint state_contains not satisfied."
        else:
            message = "Checkpoint satisfied."
        checkpoints.append(
            CheckpointOutcome(checkpoint_id=checkpoint.id, passed=passed_cp, message=message)
        )

    trajectory_listed = _trajectory_matches_allowed(tools_called, task.allowed_trajectories)
    task_success = final_ok
    tool_score = _tool_level_score(task, tools_called)
    # Trajectory is valid if listed OR final state matches with no allow-list.
    trajectory_valid = trajectory_listed or (task_success and not task.allowed_trajectories)

    if task_success and not trajectory_listed and task.allowed_trajectories:
        message = (
            "Final state matched via an alternate trajectory (not listed in allowed_trajectories)."
        )
    elif task_success:
        message = "Final state matched; workflow task succeeded."
    else:
        message = "Final state did not match expected task outcome."

    if dead_ends:
        message += f" Dead ends recorded: {dead_ends}."
    if recoveries:
        message += f" Recoveries recorded: {recoveries}."

    return WorkflowResult(
        task_id=task.id,
        passed=task_success,
        task_success=task_success,
        trajectory_valid=trajectory_valid,
        tool_level_score=tool_score,
        final_state_matched=final_ok,
        derived_final_state=final_state,
        checkpoint_outcomes=checkpoints,
        dead_end_count=dead_ends,
        recovery_count=recoveries,
        tools_called=tools_called,
        message=message,
    )


def evaluate_workflows(
    tasks: list[WorkflowTask],
    traces: list[WorkflowTrace],
) -> WorkflowReport:
    """Batch-evaluate traces; compute tool / trajectory / task level rates."""
    by_id = {task.id: task for task in tasks}
    results: list[WorkflowResult] = []
    for trace in traces:
        task = by_id.get(trace.task_id)
        if task is None:
            results.append(
                WorkflowResult(
                    task_id=trace.task_id,
                    passed=False,
                    task_success=False,
                    trajectory_valid=False,
                    tool_level_score=0.0,
                    final_state_matched=False,
                    message=f"No workflow task defined for '{trace.task_id}'.",
                )
            )
            continue
        results.append(evaluate_workflow(task, trace))

    def _avg(values: list[float]) -> float | None:
        if not values:
            return None
        return round(sum(values) / len(values), 4)

    return WorkflowReport(
        results=results,
        rates=WorkflowLevelRates(
            tool_level=_avg([item.tool_level_score for item in results]),
            trajectory_level=_avg([1.0 if item.trajectory_valid else 0.0 for item in results]),
            task_level=_avg([1.0 if item.task_success else 0.0 for item in results]),
        ),
    )


def render_workflow_report_markdown(report: WorkflowReport) -> str:
    rates = report.rates
    lines = [
        "# Workflow evaluation report",
        "",
        "### Level rates",
        "",
        f"- tool-level: `{_fmt(rates.tool_level)}`",
        f"- trajectory-level: `{_fmt(rates.trajectory_level)}`",
        f"- task-level (final state): `{_fmt(rates.task_level)}`",
        "",
        "| Task | Passed | Final state | Trajectory | Tool score | "
        "Dead ends | Recoveries | Message |",
        "| --- | --- | --- | --- | ---: | ---: | ---: | --- |",
    ]
    for item in report.results:
        message = item.message.replace("|", "\\|")
        lines.append(
            f"| `{item.task_id}` | {'yes' if item.passed else 'no'} | "
            f"{'yes' if item.final_state_matched else 'no'} | "
            f"{'yes' if item.trajectory_valid else 'no'} | "
            f"{item.tool_level_score:.0%} | {item.dead_end_count} | "
            f"{item.recovery_count} | {message} |"
        )
    lines.append("")
    return "\n".join(lines)


def _fmt(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.0%}"
