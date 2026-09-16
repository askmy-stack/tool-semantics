"""Render compatibility reports for humans and machines."""

from __future__ import annotations

import json
from typing import Any

from tool_semantics.diff import CompatibilityReport, Severity
from tool_semantics.probe_gate import ProbeGateReport, TargetProbeOutcome
from tool_semantics.probes import ModelProbeReport, ProbeMetrics, ProbeReport, StabilityReport


def render_markdown(
    report: CompatibilityReport,
    *,
    probe_gate: ProbeGateReport | None = None,
) -> str:
    """Render a GitHub-friendly Markdown compatibility report."""
    status = "compatible" if report.is_compatible else "breaking"
    counts = report.counts_by_severity()
    lines = [
        f"# Tool-Semantics report: {report.baseline} → {report.candidate}",
        "",
        f"**Result:** `{status}`",
        "",
        "| Severity | Count |",
        "| --- | ---: |",
        f"| critical | {counts['critical']} |",
        f"| breaking | {counts['breaking']} |",
        f"| warning | {counts['warning']} |",
        f"| info | {counts['info']} |",
        "",
    ]
    if not report.changes:
        lines.append("_No structural changes detected._")
        lines.append("")
    else:
        lines.extend(
            [
                "| Severity | Code | Subject | Change |",
                "| --- | --- | --- | --- |",
            ]
        )
        for change in report.changes:
            message = change.message.replace("|", "\\|")
            lines.append(
                f"| `{change.severity.value}` | `{change.code}` | `{change.subject}` | {message} |"
            )
        lines.append("")

    if probe_gate is not None and probe_gate.enabled:
        lines.append(render_probe_gate_markdown(probe_gate).rstrip())
        lines.append("")
    return "\n".join(lines)


def render_probe_gate_markdown(gate: ProbeGateReport) -> str:
    """Markdown section for probe metrics / stability attached to compare."""
    status = "FAIL" if gate.failed else "PASS"
    lines = [
        "## Behavioral probes",
        "",
        f"**Probe gate:** `{status}`",
        "",
    ]
    settings = gate.settings
    if settings:
        lines.append(
            f"- Mode: `{settings.get('mode', 'n/a')}` · "
            f"Target: `{settings.get('target', 'n/a')}` · "
            f"Trials: `{settings.get('trials', 1)}`"
        )
        if settings.get("file"):
            lines.append(f"- Probe file: `{settings['file']}`")
        lines.append("")
    for outcome in gate.targets:
        lines.extend(_render_target_probe_section(outcome))
    if gate.breaches:
        lines.append("### Threshold breaches")
        lines.append("")
        for breach in gate.breaches:
            safe = breach.replace("|", "\\|")
            lines.append(f"- {safe}")
        lines.append("")
    return "\n".join(lines)


def _render_target_probe_section(outcome: TargetProbeOutcome) -> list[str]:
    lines = [
        f"### Target: `{outcome.target}` ({outcome.mode})",
        "",
        f"- Passed: `{'yes' if outcome.passed else 'no'}`",
        "",
    ]
    if outcome.metrics is not None:
        lines.append(render_probe_metrics_markdown(outcome.metrics, title="Metrics").rstrip())
        lines.append("")
    if outcome.offline is not None:
        lines.extend(
            [
                "| Probe | Passed | Message |",
                "| --- | --- | --- |",
            ]
        )
        for offline_result in outcome.offline.results:
            message = offline_result.message.replace("|", "\\|")
            lines.append(
                f"| `{offline_result.probe_id}` | "
                f"{'yes' if offline_result.passed else 'no'} | {message} |"
            )
        lines.append("")
    if outcome.model is not None:
        lines.extend(
            [
                "| Probe | Passed | Outcome | Selected | Message |",
                "| --- | --- | --- | --- | --- |",
            ]
        )
        for model_result in outcome.model.results:
            message = model_result.message.replace("|", "\\|")
            lines.append(
                f"| `{model_result.probe_id}` | {'yes' if model_result.passed else 'no'} | "
                f"`{model_result.outcome.value}` | `{model_result.selected_tool or ''}` | "
                f"{message} |"
            )
        lines.append("")
    if outcome.stability is not None:
        lines.append(render_stability_markdown(outcome.stability).rstrip())
        lines.append("")
    return lines


def _fmt_rate(value: float | None) -> str:
    if value is None:
        return "n/a (missing data)"
    return f"{value:.1%}"


def render_offline_probe_report_markdown(report: ProbeReport, *, snapshot_label: str = "") -> str:
    """Markdown for deterministic offline probe results."""
    status = "PASS" if report.passed else "FAIL"
    lines = [
        "# Offline probe report",
        "",
        f"**Result:** `{status}`",
        "",
    ]
    if snapshot_label:
        lines.append(f"- Snapshot: `{snapshot_label}`")
        lines.append(f"- Probes: {len(report.results)}")
        lines.append(f"- Failures: {len(report.failures)}")
        lines.append("")
    lines.extend(
        [
            "| Probe | Passed | Message |",
            "| --- | --- | --- |",
        ]
    )
    for result in report.results:
        message = result.message.replace("|", "\\|")
        lines.append(f"| `{result.probe_id}` | {'yes' if result.passed else 'no'} | {message} |")
    lines.append("")
    return "\n".join(lines)


def render_offline_probe_report_json(report: ProbeReport) -> dict[str, Any]:
    return {
        "mode": "offline",
        "passed": report.passed,
        "results": [item.model_dump(mode="json") for item in report.results],
        "failure_count": len(report.failures),
    }


def render_probe_metrics_markdown(metrics: ProbeMetrics, *, title: str = "Probe metrics") -> str:
    """Markdown for tool-selection / argument-validity metrics (#46)."""
    lines = [
        f"# {title}",
        "",
        f"- Probes: {metrics.probe_count}",
        f"- Evaluated: {metrics.evaluated_count}",
        f"- Missing data: {metrics.missing_data_count}",
        f"- Failed evaluations: {metrics.failed_evaluation_count}",
        f"- Tool-selection accuracy: {_fmt_rate(metrics.tool_selection_accuracy)}",
        f"- Argument-validity rate: {_fmt_rate(metrics.argument_validity_rate)}",
        f"- Risk compliance: {_fmt_rate(metrics.risk_compliance_rate)}",
        f"- Confirmation compliance: {_fmt_rate(metrics.confirmation_compliance_rate)}",
        "",
    ]
    if metrics.per_probe:
        lines.extend(
            [
                "| Probe | Evaluated | Selection accuracy | Arg validity | Passed |",
                "| --- | ---: | ---: | ---: | --- |",
            ]
        )
        for probe_id, row in sorted(metrics.per_probe.items()):
            lines.append(
                f"| `{probe_id}` | {row.get('evaluated', 0)} | "
                f"{_fmt_rate(row.get('tool_selection_accuracy'))} | "
                f"{_fmt_rate(row.get('argument_validity_rate'))} | "
                f"{'yes' if row.get('passed') else 'no'} |"
            )
        lines.append("")
    return "\n".join(lines)


def render_probe_metrics_json(metrics: ProbeMetrics) -> dict[str, Any]:
    return metrics.model_dump(mode="json")


def render_model_probe_report_markdown(report: ModelProbeReport) -> str:
    metrics_section = ""
    from tool_semantics.probes import compute_probe_metrics

    metrics = compute_probe_metrics(report.results)
    metrics_section = render_probe_metrics_markdown(metrics)
    lines = [
        metrics_section.rstrip(),
        "",
        "## Per-probe results",
        "",
        "| Probe | Passed | Outcome | Selected tool | Message |",
        "| --- | --- | --- | --- | --- |",
    ]
    for result in report.results:
        message = result.message.replace("|", "\\|")
        lines.append(
            f"| `{result.probe_id}` | {'yes' if result.passed else 'no'} | "
            f"`{result.outcome.value}` | `{result.selected_tool or ''}` | {message} |"
        )
    lines.append("")
    return "\n".join(lines)


def render_stability_markdown(report: StabilityReport) -> str:
    """Markdown distinguishing unstable probes from deterministic failures (#47)."""
    lines = [
        "# Probe stability report",
        "",
        f"- Trials: {report.trial_count}",
        f"- Seed: {report.seed if report.seed is not None else 'n/a'}",
        "",
        render_probe_metrics_markdown(report.metrics, title="Aggregate metrics").rstrip(),
        "",
        "## Stability by probe",
        "",
        "| Probe | Stability | Unstable | Deterministic failure | Aggregate passed | Message |",
        "| --- | ---: | --- | --- | --- | --- |",
    ]
    for summary in report.summaries:
        safe_message = summary.message.replace("|", "\\|")
        lines.append(
            f"| `{summary.probe_id}` | {summary.stability_score:.2f} | "
            f"{'yes' if summary.unstable else 'no'} | "
            f"{'yes' if summary.deterministic_failure else 'no'} | "
            f"{'yes' if summary.aggregate_passed else 'no'} | "
            f"{safe_message} |"
        )
    lines.append("")
    unstable = [item for item in report.summaries if item.unstable]
    deterministic = [item for item in report.summaries if item.deterministic_failure]
    if unstable:
        lines.append("### Unstable probes")
        lines.append("")
        for item in unstable:
            lines.append(f"- `{item.probe_id}` (score={item.stability_score:.2f})")
        lines.append("")
    if deterministic:
        lines.append("### Deterministic failures")
        lines.append("")
        for item in deterministic:
            lines.append(f"- `{item.probe_id}`: {item.message}")
        lines.append("")
    return "\n".join(lines)


def render_stability_json(report: StabilityReport) -> str:
    return json.dumps(report.model_dump(mode="json"), indent=2) + "\n"


def severity_style(severity: Severity) -> str:
    return {
        Severity.INFO: "cyan",
        Severity.WARNING: "yellow",
        Severity.BREAKING: "red",
        Severity.CRITICAL: "bold red",
    }[severity]
