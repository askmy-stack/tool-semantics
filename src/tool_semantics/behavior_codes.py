"""Emit behavior.* Change entries from model-backed probe outcomes (#61)."""

from __future__ import annotations

from tool_semantics.diff import Change, CompatibilityReport, Severity
from tool_semantics.probes import (
    ModelProbeOutcome,
    ModelProbeReport,
    ModelProbeResult,
    StabilityReport,
)

# Stable catalog — keep in sync with docs/change-codes.md.
BEHAVIOR_TOOL_SELECTION_FAILED = "behavior.tool_selection_failed"
BEHAVIOR_ARGUMENTS_INVALID = "behavior.arguments_invalid"
BEHAVIOR_UNSTABLE_PROBE = "behavior.unstable_probe"
BEHAVIOR_DETERMINISTIC_FAILURE = "behavior.deterministic_failure"
BEHAVIOR_RISK_EXPECTATION_FAILED = "behavior.risk_expectation_failed"
BEHAVIOR_CONFIRMATION_EXPECTATION_FAILED = "behavior.confirmation_expectation_failed"
BEHAVIOR_MISSING_DATA = "behavior.missing_data"
BEHAVIOR_EVALUATION_FAILED = "behavior.evaluation_failed"


def changes_from_model_probe_result(result: ModelProbeResult) -> list[Change]:
    """Map one model probe result to zero or more behavior.* changes.

    SKIPPED and successful outcomes emit nothing. MISSING_DATA emits info only
    (never breaking) so absent model calls do not false-fail CI.
    """
    if result.outcome == ModelProbeOutcome.SKIPPED:
        return []
    if result.outcome == ModelProbeOutcome.MISSING_DATA:
        return [
            Change(
                severity=Severity.INFO,
                code=BEHAVIOR_MISSING_DATA,
                subject=result.probe_id,
                message=(
                    f"Probe '{result.probe_id}' returned missing model data "
                    f"(no tool call or incomplete response): {result.message}"
                ),
            )
        ]
    if result.outcome == ModelProbeOutcome.FAILED_EVALUATION:
        return [
            Change(
                severity=Severity.WARNING,
                code=BEHAVIOR_EVALUATION_FAILED,
                subject=result.probe_id,
                message=f"Probe '{result.probe_id}' evaluation failed: {result.message}",
            )
        ]

    changes: list[Change] = []
    if result.tool_selection_correct is False:
        changes.append(
            Change(
                severity=Severity.BREAKING,
                code=BEHAVIOR_TOOL_SELECTION_FAILED,
                subject=result.probe_id,
                message=(
                    f"Probe '{result.probe_id}' selected wrong tool "
                    f"('{result.selected_tool or 'none'}'): {result.message}"
                ),
            )
        )
    if result.arguments_valid is False:
        changes.append(
            Change(
                severity=Severity.BREAKING,
                code=BEHAVIOR_ARGUMENTS_INVALID,
                subject=result.probe_id,
                message=(
                    f"Probe '{result.probe_id}' produced invalid arguments "
                    f"{result.arguments}: {result.message}"
                ),
            )
        )
    if result.risk_compliant is False:
        changes.append(
            Change(
                severity=Severity.BREAKING,
                code=BEHAVIOR_RISK_EXPECTATION_FAILED,
                subject=result.probe_id,
                message=(
                    f"Probe '{result.probe_id}' violated risk expectation "
                    f"(selected '{result.selected_tool or 'none'}')."
                ),
            )
        )
    if result.confirmation_compliant is False:
        changes.append(
            Change(
                severity=Severity.WARNING,
                code=BEHAVIOR_CONFIRMATION_EXPECTATION_FAILED,
                subject=result.probe_id,
                message=(
                    f"Probe '{result.probe_id}' violated confirmation expectation "
                    f"(selected '{result.selected_tool or 'none'}')."
                ),
            )
        )
    return changes


def changes_from_model_probe_report(report: ModelProbeReport) -> list[Change]:
    out: list[Change] = []
    for result in report.results:
        out.extend(changes_from_model_probe_result(result))
    return out


def changes_from_stability_report(report: StabilityReport) -> list[Change]:
    """Map stability summaries to distinct unstable vs deterministic codes (#47/#61)."""
    changes: list[Change] = []
    for summary in report.summaries:
        if summary.deterministic_failure:
            changes.append(
                Change(
                    severity=Severity.BREAKING,
                    code=BEHAVIOR_DETERMINISTIC_FAILURE,
                    subject=summary.probe_id,
                    message=(
                        f"Probe '{summary.probe_id}' failed deterministically across "
                        f"{report.trial_count} trials: {summary.message}"
                    ),
                )
            )
        elif summary.unstable:
            changes.append(
                Change(
                    severity=Severity.WARNING,
                    code=BEHAVIOR_UNSTABLE_PROBE,
                    subject=summary.probe_id,
                    message=(
                        f"Probe '{summary.probe_id}' is unstable across "
                        f"{report.trial_count} trials "
                        f"(stability={summary.stability_score:.2f}): {summary.message}"
                    ),
                )
            )
    return changes


def merge_behavior_changes(
    report: CompatibilityReport, behavior_changes: list[Change]
) -> CompatibilityReport:
    """Attach probe-derived changes onto a structural compatibility report."""
    if not behavior_changes:
        return report
    return CompatibilityReport(
        baseline=report.baseline,
        candidate=report.candidate,
        changes=[*report.changes, *behavior_changes],
    )
