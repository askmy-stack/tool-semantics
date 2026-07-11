"""Render compatibility reports for humans and machines."""

from __future__ import annotations

from tool_semantics.diff import CompatibilityReport, Severity


def render_markdown(report: CompatibilityReport) -> str:
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
        return "\n".join(lines)

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
    return "\n".join(lines)


def severity_style(severity: Severity) -> str:
    return {
        Severity.INFO: "cyan",
        Severity.WARNING: "yellow",
        Severity.BREAKING: "red",
        Severity.CRITICAL: "bold red",
    }[severity]
