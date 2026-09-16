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
    assert "## Tools" in markdown
    assert "## Prompts" in markdown
    assert "## Resources" in markdown


def test_counts_by_severity() -> None:
    baseline = capture_manifest(Path("examples/github_server_v1.json"))
    candidate = capture_manifest(Path("examples/github_server_v2.json"))
    report = compare_snapshots(baseline, candidate)
    counts = report.counts_by_severity()
    assert counts["breaking"] >= 1
    assert sum(counts.values()) == len(report.changes)


def test_detects_output_schema_added_removed_changed() -> None:
    baseline = capture_manifest(Path("examples/github_server_v1.json"))
    candidate = capture_manifest(Path("examples/github_server_v1.json"))
    search = next(tool for tool in candidate.tools if tool.name == "search_issues")
    search.output_schema = {"type": "object", "properties": {"items": {"type": "array"}}}
    report = compare_snapshots(baseline, candidate)
    assert any(change.code == "tool.output_schema_added" for change in report.changes)
    assert report.is_compatible

    baseline_with = capture_manifest(Path("examples/github_server_v1.json"))
    candidate_changed = capture_manifest(Path("examples/github_server_v1.json"))
    for tool in baseline_with.tools:
        if tool.name == "search_issues":
            tool.output_schema = {"type": "object", "properties": {"items": {"type": "array"}}}
    for tool in candidate_changed.tools:
        if tool.name == "search_issues":
            tool.output_schema = {"type": "object", "properties": {"total": {"type": "integer"}}}
    report_changed = compare_snapshots(baseline_with, candidate_changed)
    assert any(change.code == "tool.output_schema_changed" for change in report_changed.changes)
    assert not report_changed.is_compatible

    candidate_removed = capture_manifest(Path("examples/github_server_v1.json"))
    report_removed = compare_snapshots(baseline_with, candidate_removed)
    assert any(change.code == "tool.output_schema_removed" for change in report_removed.changes)
    assert not report_removed.is_compatible


def test_detects_parameter_default_changed_without_schema_changed() -> None:
    baseline = capture_manifest(Path("examples/github_server_v1.json"))
    candidate = capture_manifest(Path("examples/github_server_v1.json"))
    search = next(tool for tool in candidate.tools if tool.name == "search_issues")
    state = next(parameter for parameter in search.parameters if parameter.name == "state")
    state.schema_ = {"type": "string", "enum": ["open", "closed"], "default": "closed"}
    report = compare_snapshots(baseline, candidate)
    assert any(change.code == "parameter.default_changed" for change in report.changes)
    assert not any(change.code == "parameter.schema_changed" for change in report.changes)
    assert report.is_compatible


def test_detects_parameter_default_added_and_removed() -> None:
    baseline = capture_manifest(Path("examples/github_server_v1.json"))
    candidate = capture_manifest(Path("examples/github_server_v1.json"))
    search = next(tool for tool in candidate.tools if tool.name == "search_issues")
    state = next(parameter for parameter in search.parameters if parameter.name == "state")
    state.schema_ = {"type": "string", "enum": ["open", "closed"]}
    report = compare_snapshots(baseline, candidate)
    assert any(
        change.code == "parameter.default_changed" and "removed" in change.message
        for change in report.changes
    )

    baseline_no_default = capture_manifest(Path("examples/github_server_v1.json"))
    search_base = next(tool for tool in baseline_no_default.tools if tool.name == "search_issues")
    state_base = next(
        parameter for parameter in search_base.parameters if parameter.name == "state"
    )
    state_base.schema_ = {"type": "string", "enum": ["open", "closed"]}
    candidate_added = capture_manifest(Path("examples/github_server_v1.json"))
    report_added = compare_snapshots(baseline_no_default, candidate_added)
    assert any(
        change.code == "parameter.default_changed" and "added" in change.message
        for change in report_added.changes
    )


def test_prompt_and_resource_structural_diffs() -> None:
    baseline = capture_manifest(Path("examples/mcp_prompts_resources_v1.json"))
    candidate = capture_manifest(Path("examples/mcp_prompts_resources_v2.json"))
    assert [p.name for p in baseline.prompts] == ["draft_reply", "summarize"]
    assert [r.uri for r in baseline.resources] == ["file:///tmp/readme.md", "memo://notes"]

    report = compare_snapshots(baseline, candidate)
    codes = {change.code for change in report.changes}
    assert "prompt.renamed" in codes  # summarize -> summarize_text
    assert "prompt.removed" in codes  # draft_reply
    assert "prompt.added" in codes  # translate
    assert "prompt.argument.became_required" in codes  # style
    assert "prompt.argument.added" in codes  # max_words
    assert "resource.renamed" in codes  # memo://notes -> memo://personal-notes
    assert "resource.mime_type_changed" in codes
    assert "resource.description_changed" in codes
    assert not report.is_compatible

    markdown = render_markdown(report)
    assert "## Prompts" in markdown
    assert "## Resources" in markdown
    assert "`prompt.renamed`" in markdown
    assert "`resource.mime_type_changed`" in markdown


def test_prompt_argument_normalization_is_stable() -> None:
    baseline = capture_manifest(Path("examples/mcp_prompts_resources_v1.json"))
    # Arguments should be sorted by name regardless of manifest order.
    summarize = next(prompt for prompt in baseline.prompts if prompt.name == "summarize")
    assert [arg["name"] for arg in summarize.arguments] == ["style", "text"]
