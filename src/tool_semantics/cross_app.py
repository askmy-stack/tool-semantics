"""Cross-application / multi-namespace workflow benchmarks (#112).

Tasks may span multiple tool namespaces (e.g. Drive → Gmail → Calendar → CRM).
When a whole workflow fails after interface changes, attribution names the
namespace most likely responsible.
"""

from __future__ import annotations

from copy import deepcopy
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from tool_semantics.diff import Change, CompatibilityReport, Severity


class AttributionConfidence(StrEnum):
    CONFIRMED = "confirmed"
    LIKELY = "likely"
    PROBABLE = "probable"
    UNCLEAR = "unclear"


class ToolNamespace(BaseModel):
    """One application / tool catalog slice in a cross-app task."""

    id: str
    display_name: str = ""
    tools: list[str] = Field(default_factory=list)


class CrossAppStep(BaseModel):
    """One simulated tool call tagged with its namespace."""

    tool: str
    namespace: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    state_patch: dict[str, Any] = Field(default_factory=dict)
    note: str | None = None


class CrossAppTask(BaseModel):
    """Multi-namespace task: final state is primary success; hops are diagnostics."""

    id: str
    intent: str
    namespaces: list[ToolNamespace] = Field(default_factory=list)
    # Expected ordered namespace hops (subset of namespaces used).
    required_namespace_sequence: list[str] = Field(default_factory=list)
    final_state: dict[str, Any] = Field(default_factory=dict)
    initial_state: dict[str, Any] = Field(default_factory=dict)
    # Optional per-namespace required tools (must appear somewhere in the trace).
    namespace_required_tools: dict[str, list[str]] = Field(default_factory=dict)


class CrossAppTrace(BaseModel):
    task_id: str
    steps: list[CrossAppStep] = Field(default_factory=list)
    final_state: dict[str, Any] | None = None


class NamespaceOutcome(BaseModel):
    namespace: str
    tools_called: list[str] = Field(default_factory=list)
    required_tools_met: bool = True
    missing_tools: list[str] = Field(default_factory=list)
    message: str = ""


class FailureAttribution(BaseModel):
    namespace: str | None = None
    confidence: AttributionConfidence = AttributionConfidence.UNCLEAR
    reason: str = ""
    change_codes: list[str] = Field(default_factory=list)
    step_index: int | None = None
    tool: str | None = None


class CrossAppResult(BaseModel):
    task_id: str
    passed: bool
    final_state_matched: bool
    namespace_sequence_ok: bool
    derived_final_state: dict[str, Any] = Field(default_factory=dict)
    namespace_outcomes: list[NamespaceOutcome] = Field(default_factory=list)
    attribution: FailureAttribution | None = None
    message: str = ""


class CrossAppReport(BaseModel):
    results: list[CrossAppResult] = Field(default_factory=list)

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


def namespace_for_tool(task: CrossAppTask, tool: str) -> str | None:
    for ns in task.namespaces:
        if tool in ns.tools:
            return ns.id
    return None


def derive_final_state(task: CrossAppTask, trace: CrossAppTrace) -> dict[str, Any]:
    if trace.final_state is not None:
        return deepcopy(trace.final_state)
    state = deepcopy(task.initial_state)
    for step in trace.steps:
        if step.state_patch:
            state = _deep_update(state, step.state_patch)
    return state


def _namespace_outcomes(task: CrossAppTask, trace: CrossAppTrace) -> list[NamespaceOutcome]:
    by_ns: dict[str, list[str]] = {ns.id: [] for ns in task.namespaces}
    for step in trace.steps:
        by_ns.setdefault(step.namespace, []).append(step.tool)
    outcomes: list[NamespaceOutcome] = []
    for ns in task.namespaces:
        called = by_ns.get(ns.id, [])
        required = task.namespace_required_tools.get(ns.id, [])
        missing = [name for name in required if name not in called]
        ok = not missing
        message = "ok" if ok else f"Missing required tools: {', '.join(missing)}"
        outcomes.append(
            NamespaceOutcome(
                namespace=ns.id,
                tools_called=called,
                required_tools_met=ok,
                missing_tools=missing,
                message=message,
            )
        )
    return outcomes


def _sequence_ok(task: CrossAppTask, trace: CrossAppTrace) -> bool:
    if not task.required_namespace_sequence:
        return True
    observed = [step.namespace for step in trace.steps]
    it = iter(observed)
    return all(ns in it for ns in task.required_namespace_sequence)


def _breaking_changes(report: CompatibilityReport | None) -> list[Change]:
    if report is None:
        return []
    return [
        change
        for change in report.changes
        if change.severity in (Severity.BREAKING, Severity.CRITICAL)
    ]


def attribute_failure(
    task: CrossAppTask,
    trace: CrossAppTrace,
    *,
    namespace_diffs: dict[str, CompatibilityReport] | None = None,
    first_failed_step: int | None = None,
) -> FailureAttribution:
    """Name the interface change / hop most likely responsible for workflow failure.

    Preference order:
    1. Namespace with breaking/critical structural diffs whose tools appear at/after failure
    2. First namespace in the required sequence whose required tools were missing
    3. Namespace of the first failed step (when provided)
    """
    diffs = namespace_diffs or {}
    outcomes = {item.namespace: item for item in _namespace_outcomes(task, trace)}

    # 1) Structural diffs on namespaces used in the trace.
    candidates: list[tuple[str, list[Change], int]] = []
    for ns_id, report in diffs.items():
        breaking = _breaking_changes(report)
        if not breaking:
            continue
        # Prefer namespaces whose tools were actually invoked.
        used = any(step.namespace == ns_id for step in trace.steps)
        score = 2 if used else 1
        if first_failed_step is not None:
            later = any(
                step.namespace == ns_id
                for index, step in enumerate(trace.steps)
                if index >= first_failed_step
            )
            if later:
                score += 2
        candidates.append((ns_id, breaking, score))
    if candidates:
        candidates.sort(key=lambda item: item[2], reverse=True)
        ns_id, breaking, _score = candidates[0]
        codes = [change.code for change in breaking]
        return FailureAttribution(
            namespace=ns_id,
            confidence=AttributionConfidence.LIKELY,
            reason=(
                f"Breaking changes in `{ns_id}` "
                f"({', '.join(codes[:5])}) align with the failed cross-app workflow."
            ),
            change_codes=codes,
            step_index=first_failed_step,
        )

    # 2) Missing required tools per namespace (in sequence order).
    order = task.required_namespace_sequence or [ns.id for ns in task.namespaces]
    for ns_id in order:
        outcome = outcomes.get(ns_id)
        if outcome and not outcome.required_tools_met:
            return FailureAttribution(
                namespace=ns_id,
                confidence=AttributionConfidence.CONFIRMED,
                reason=outcome.message,
                change_codes=[],
                tool=outcome.missing_tools[0] if outcome.missing_tools else None,
            )

    # 3) Explicit failed step.
    if first_failed_step is not None and 0 <= first_failed_step < len(trace.steps):
        step = trace.steps[first_failed_step]
        return FailureAttribution(
            namespace=step.namespace,
            confidence=AttributionConfidence.PROBABLE,
            reason=f"First failed hop at step {first_failed_step} tool `{step.tool}`.",
            step_index=first_failed_step,
            tool=step.tool,
        )

    return FailureAttribution(
        namespace=None,
        confidence=AttributionConfidence.UNCLEAR,
        reason="Unable to attribute failure to a single namespace.",
    )


def evaluate_cross_app(
    task: CrossAppTask,
    trace: CrossAppTrace,
    *,
    namespace_diffs: dict[str, CompatibilityReport] | None = None,
    first_failed_step: int | None = None,
) -> CrossAppResult:
    """Evaluate a multi-namespace workflow fixture (no live MCP execution)."""
    if trace.task_id != task.id:
        return CrossAppResult(
            task_id=task.id,
            passed=False,
            final_state_matched=False,
            namespace_sequence_ok=False,
            message=f"Trace task_id '{trace.task_id}' does not match task '{task.id}'.",
            attribution=FailureAttribution(
                confidence=AttributionConfidence.CONFIRMED,
                reason="task_id mismatch",
            ),
        )

    # Fill missing namespace tags from the catalog when possible.
    normalized_steps: list[CrossAppStep] = []
    for step in trace.steps:
        ns = step.namespace or namespace_for_tool(task, step.tool) or ""
        normalized_steps.append(step.model_copy(update={"namespace": ns}))
    normalized = CrossAppTrace(
        task_id=trace.task_id,
        steps=normalized_steps,
        final_state=trace.final_state,
    )

    final_state = derive_final_state(task, normalized)
    final_ok = _state_contains(final_state, task.final_state) if task.final_state else True
    sequence_ok = _sequence_ok(task, normalized)
    outcomes = _namespace_outcomes(task, normalized)
    tools_ok = all(item.required_tools_met for item in outcomes)
    passed = final_ok and sequence_ok and tools_ok

    attribution = None
    message = "Cross-app workflow passed."
    if not passed:
        attribution = attribute_failure(
            task,
            normalized,
            namespace_diffs=namespace_diffs,
            first_failed_step=first_failed_step,
        )
        parts: list[str] = []
        if not final_ok:
            parts.append("final state mismatch")
        if not sequence_ok:
            parts.append("namespace sequence incomplete")
        if not tools_ok:
            parts.append("namespace required tools missing")
        message = "Cross-app workflow failed: " + "; ".join(parts)
        if attribution and attribution.namespace:
            message += f" (attributed to `{attribution.namespace}`)"

    return CrossAppResult(
        task_id=task.id,
        passed=passed,
        final_state_matched=final_ok,
        namespace_sequence_ok=sequence_ok,
        derived_final_state=final_state,
        namespace_outcomes=outcomes,
        attribution=attribution,
        message=message,
    )


def evaluate_cross_app_suite(
    tasks: list[CrossAppTask],
    traces: list[CrossAppTrace],
    *,
    namespace_diffs: dict[str, CompatibilityReport] | None = None,
) -> CrossAppReport:
    by_id = {trace.task_id: trace for trace in traces}
    results: list[CrossAppResult] = []
    for task in tasks:
        trace = by_id.get(task.id)
        if trace is None:
            results.append(
                CrossAppResult(
                    task_id=task.id,
                    passed=False,
                    final_state_matched=False,
                    namespace_sequence_ok=False,
                    message=f"No trace provided for task '{task.id}'.",
                    attribution=FailureAttribution(
                        confidence=AttributionConfidence.CONFIRMED,
                        reason="missing trace",
                    ),
                )
            )
            continue
        results.append(evaluate_cross_app(task, trace, namespace_diffs=namespace_diffs))
    return CrossAppReport(results=results)


def render_cross_app_markdown(report: CrossAppReport) -> str:
    lines = [
        "## Cross-application workflows",
        "",
        "| Task | Passed | Final state | Sequence | Attribution | Message |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for item in report.results:
        attr = "—"
        if item.attribution and item.attribution.namespace:
            attr = f"`{item.attribution.namespace}` ({item.attribution.confidence.value})"
        message = item.message.replace("|", "\\|")
        lines.append(
            f"| `{item.task_id}` | {'yes' if item.passed else 'no'} | "
            f"{'yes' if item.final_state_matched else 'no'} | "
            f"{'yes' if item.namespace_sequence_ok else 'no'} | "
            f"{attr} | {message} |"
        )
    lines.append("")
    return "\n".join(lines)
