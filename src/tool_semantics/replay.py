"""Replay agent traces against a candidate snapshot (#84).

Modes:
- ``offline`` (default): DETERMINISTIC — tool still exists and prior arguments
  still satisfy the candidate schema.
- ``model``: MODEL-BASED — opt-in re-selection via ``ModelRunner``; compares the
  newly chosen tool to the recorded ``selected_tool``.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from tool_semantics.models import InterfaceSnapshot, ToolContract
from tool_semantics.probes import _tools_as_openai_schemas
from tool_semantics.runner import ModelRunner, RunnerConfig
from tool_semantics.traces import AgentTrace, TraceStep


class ReplayMode(StrEnum):
    OFFLINE = "offline"
    MODEL = "model"


class ReplayEvidence(StrEnum):
    DETERMINISTIC = "DETERMINISTIC"
    MODEL_BASED = "MODEL-BASED"


class ReplayStatus(StrEnum):
    OK = "ok"
    CHANGED = "changed"
    FAILED = "failed"


class StepReplayResult(BaseModel):
    step_index: int
    intent: str
    recorded_tool: str
    status: ReplayStatus
    evidence: ReplayEvidence
    message: str
    tool_present: bool | None = None
    arguments_valid: bool | None = None
    reselected_tool: str | None = None
    selection_match: bool | None = None


class TraceReplayResult(BaseModel):
    trace_id: str | None = None
    intent: str
    status: ReplayStatus
    mode: ReplayMode
    steps: list[StepReplayResult] = Field(default_factory=list)
    message: str = ""


class ReplayReport(BaseModel):
    mode: ReplayMode
    candidate: str
    results: list[TraceReplayResult] = Field(default_factory=list)

    @property
    def counts(self) -> dict[str, int]:
        counts = {status.value: 0 for status in ReplayStatus}
        for item in self.results:
            counts[item.status.value] += 1
        return counts

    @property
    def passed(self) -> bool:
        return all(item.status is ReplayStatus.OK for item in self.results)


def _tool_map(snapshot: InterfaceSnapshot) -> dict[str, ToolContract]:
    return {tool.name: tool for tool in snapshot.tools}


def _arguments_still_valid(tool: ToolContract, arguments: dict[str, Any]) -> tuple[bool, str]:
    param_names = {parameter.name for parameter in tool.parameters}
    required = {parameter.name for parameter in tool.parameters if parameter.required}
    unknown = sorted(name for name in arguments if name not in param_names)
    if unknown:
        return False, f"Unknown argument(s) for '{tool.name}': {', '.join(unknown)}"
    missing = sorted(required - set(arguments))
    if missing:
        return False, f"Missing required argument(s) for '{tool.name}': {', '.join(missing)}"
    # Lightweight type / enum checks when the schema declares them.
    for parameter in tool.parameters:
        if parameter.name not in arguments:
            continue
        value = arguments[parameter.name]
        schema = parameter.schema_
        expected_type = schema.get("type")
        if expected_type == "string" and not isinstance(value, str):
            return False, f"Argument '{parameter.name}' expected string"
        if expected_type == "integer" and not isinstance(value, int):
            return False, f"Argument '{parameter.name}' expected integer"
        if expected_type == "number" and not isinstance(value, int | float):
            return False, f"Argument '{parameter.name}' expected number"
        if expected_type == "boolean" and not isinstance(value, bool):
            return False, f"Argument '{parameter.name}' expected boolean"
        enum_values = schema.get("enum")
        if isinstance(enum_values, list) and value not in enum_values:
            return False, f"Argument '{parameter.name}' value not in enum"
    return True, "Arguments still validate against the candidate schema."


def _replay_step_offline(
    step: TraceStep,
    *,
    step_index: int,
    parent_intent: str,
    tools: dict[str, ToolContract],
) -> StepReplayResult:
    intent = step.intent or parent_intent
    tool = tools.get(step.selected_tool)
    if tool is None:
        return StepReplayResult(
            step_index=step_index,
            intent=intent,
            recorded_tool=step.selected_tool,
            status=ReplayStatus.FAILED,
            evidence=ReplayEvidence.DETERMINISTIC,
            message=f"Recorded tool '{step.selected_tool}' is absent from the candidate snapshot.",
            tool_present=False,
            arguments_valid=False,
        )
    valid, detail = _arguments_still_valid(tool, step.arguments)
    if not valid:
        return StepReplayResult(
            step_index=step_index,
            intent=intent,
            recorded_tool=step.selected_tool,
            status=ReplayStatus.FAILED,
            evidence=ReplayEvidence.DETERMINISTIC,
            message=detail,
            tool_present=True,
            arguments_valid=False,
        )
    return StepReplayResult(
        step_index=step_index,
        intent=intent,
        recorded_tool=step.selected_tool,
        status=ReplayStatus.OK,
        evidence=ReplayEvidence.DETERMINISTIC,
        message=detail,
        tool_present=True,
        arguments_valid=True,
    )


def _replay_step_model(
    step: TraceStep,
    *,
    step_index: int,
    parent_intent: str,
    snapshot: InterfaceSnapshot,
    runner: ModelRunner,
) -> StepReplayResult:
    intent = step.intent or parent_intent
    tools = _tool_map(snapshot)
    offline = _replay_step_offline(
        step, step_index=step_index, parent_intent=parent_intent, tools=tools
    )
    # Deterministic schema failure still wins — do not hide with model noise.
    if offline.status is ReplayStatus.FAILED:
        return offline

    schemas = _tools_as_openai_schemas(snapshot)
    system = (
        "You are an agent that must choose exactly one tool for the user intent. "
        "Prefer the tool that best matches the request."
    )
    try:
        response = runner.complete(
            system=system,
            user=intent,
            tools=schemas,
            config=RunnerConfig(temperature=0.0),
        )
    except Exception as exc:  # noqa: BLE001 — surface runner failures in the report
        return StepReplayResult(
            step_index=step_index,
            intent=intent,
            recorded_tool=step.selected_tool,
            status=ReplayStatus.FAILED,
            evidence=ReplayEvidence.MODEL_BASED,
            message=f"Model re-selection failed: {exc}",
            tool_present=True,
            arguments_valid=True,
        )

    selected = None
    if response.tool_calls:
        selected = response.tool_calls[0].name
    if selected is None:
        return StepReplayResult(
            step_index=step_index,
            intent=intent,
            recorded_tool=step.selected_tool,
            status=ReplayStatus.CHANGED,
            evidence=ReplayEvidence.MODEL_BASED,
            message="Model did not select any tool on re-selection.",
            tool_present=True,
            arguments_valid=True,
            reselected_tool=None,
            selection_match=False,
        )
    if selected != step.selected_tool:
        return StepReplayResult(
            step_index=step_index,
            intent=intent,
            recorded_tool=step.selected_tool,
            status=ReplayStatus.CHANGED,
            evidence=ReplayEvidence.MODEL_BASED,
            message=(f"Model re-selected '{selected}' instead of recorded '{step.selected_tool}'."),
            tool_present=True,
            arguments_valid=True,
            reselected_tool=selected,
            selection_match=False,
        )
    return StepReplayResult(
        step_index=step_index,
        intent=intent,
        recorded_tool=step.selected_tool,
        status=ReplayStatus.OK,
        evidence=ReplayEvidence.MODEL_BASED,
        message="Model re-selected the recorded tool; arguments still validate.",
        tool_present=True,
        arguments_valid=True,
        reselected_tool=selected,
        selection_match=True,
    )


def _rollup_status(steps: list[StepReplayResult]) -> ReplayStatus:
    if any(step.status is ReplayStatus.FAILED for step in steps):
        return ReplayStatus.FAILED
    if any(step.status is ReplayStatus.CHANGED for step in steps):
        return ReplayStatus.CHANGED
    return ReplayStatus.OK


def replay_trace(
    trace: AgentTrace,
    snapshot: InterfaceSnapshot,
    *,
    mode: ReplayMode = ReplayMode.OFFLINE,
    runner: ModelRunner | None = None,
) -> TraceReplayResult:
    """Replay one trace against a candidate snapshot."""
    if mode is ReplayMode.MODEL and runner is None:
        raise ValueError("model replay mode requires a ModelRunner")

    steps_out: list[StepReplayResult] = []
    tools = _tool_map(snapshot)
    for index, step in enumerate(trace.effective_steps()):
        if mode is ReplayMode.OFFLINE:
            steps_out.append(
                _replay_step_offline(
                    step,
                    step_index=index,
                    parent_intent=trace.intent,
                    tools=tools,
                )
            )
        else:
            assert runner is not None
            steps_out.append(
                _replay_step_model(
                    step,
                    step_index=index,
                    parent_intent=trace.intent,
                    snapshot=snapshot,
                    runner=runner,
                )
            )

    status = _rollup_status(steps_out)
    if status is ReplayStatus.OK:
        message = "All steps passed."
    elif status is ReplayStatus.CHANGED:
        message = "Behavioral change detected (model re-selection drift)."
    else:
        message = "Replay failed (tool missing or arguments invalid)."
    return TraceReplayResult(
        trace_id=trace.id,
        intent=trace.intent,
        status=status,
        mode=mode,
        steps=steps_out,
        message=message,
    )


def replay_traces(
    traces: list[AgentTrace],
    snapshot: InterfaceSnapshot,
    *,
    mode: ReplayMode = ReplayMode.OFFLINE,
    runner: ModelRunner | None = None,
) -> ReplayReport:
    """Batch-replay traces; aggregate ok / changed / failed counts."""
    results = [replay_trace(trace, snapshot, mode=mode, runner=runner) for trace in traces]
    return ReplayReport(
        mode=mode,
        candidate=snapshot.server_version or snapshot.server_name,
        results=results,
    )


def render_replay_markdown(report: ReplayReport) -> str:
    counts = report.counts
    lines = [
        "# Tool-Semantics trace replay",
        "",
        f"**Mode:** `{report.mode.value}`",
        f"**Candidate:** `{report.candidate}`",
        "",
        "### Counts",
        "",
        f"- ok: `{counts['ok']}`",
        f"- changed: `{counts['changed']}`",
        f"- failed: `{counts['failed']}`",
        "",
    ]
    for item in report.results:
        label = item.trace_id or item.intent[:60]
        lines.append(f"## `{label}` — `{item.status.value}`")
        lines.append("")
        lines.append(item.message)
        lines.append("")
        lines.extend(
            [
                "| Step | Recorded tool | Status | Evidence | Detail |",
                "| ---: | --- | --- | --- | --- |",
            ]
        )
        for step in item.steps:
            detail = step.message.replace("|", "\\|")
            lines.append(
                f"| {step.step_index} | `{step.recorded_tool}` | `{step.status.value}` | "
                f"`{step.evidence.value}` | {detail} |"
            )
        lines.append("")
    return "\n".join(lines)
