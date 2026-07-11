from pathlib import Path

from tool_semantics.diff import Severity, compare_snapshots
from tool_semantics.report import render_markdown
from tool_semantics.scanner import capture_manifest


def test_detects_breaking_changes() -> None:
    baseline = capture_manifest(Path("examples/github_server_v1.json"))
    candidate = capture_manifest(Path("examples/github_server_v2.json"))
    report = compare_snapshots(baseline, candidate)
    assert not report.is_compatible
    assert any(
        change.code == "tool.removed" and change.subject == "search_issues"
        for change in report.changes
    )
    assert any(
        change.severity == Severity.BREAKING and change.code == "parameter.added_required"
        for change in report.changes
    )


def test_detects_description_change() -> None:
    baseline = capture_manifest(Path("examples/github_server_v1.json"))
    candidate = capture_manifest(Path("examples/github_server_v2.json"))
    report = compare_snapshots(baseline, candidate)
    assert any(change.code == "tool.description_changed" for change in report.changes)


def test_detects_enum_value_removal() -> None:
    baseline = capture_manifest(Path("examples/github_server_v1.json"))
    candidate = capture_manifest(Path("examples/github_server_v1.json"))
    # Mutate candidate enum in-memory
    search = next(tool for tool in candidate.tools if tool.name == "search_issues")
    state = next(parameter for parameter in search.parameters if parameter.name == "state")
    state.schema_ = {"type": "string", "enum": ["open"], "default": "open"}
    report = compare_snapshots(baseline, candidate)
    assert any(change.code == "parameter.enum_values_removed" for change in report.changes)
    assert any("closed" in change.message for change in report.changes)


def test_markdown_report_includes_summary() -> None:
    baseline = capture_manifest(Path("examples/github_server_v1.json"))
    candidate = capture_manifest(Path("examples/github_server_v2.json"))
    report = compare_snapshots(baseline, candidate)
    markdown = render_markdown(report)
    assert "# Tool-Semantics report:" in markdown
    assert "**Result:** `breaking`" in markdown
    assert "| Severity | Count |" in markdown
