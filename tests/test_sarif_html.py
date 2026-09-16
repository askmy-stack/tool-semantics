"""Tests for optional SARIF / HTML report outputs (#99)."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from tool_semantics.cli import app
from tool_semantics.diff import Change, CompatibilityReport, Severity
from tool_semantics.html_report import render_html_report
from tool_semantics.sarif import SARIF_SCHEMA, SARIF_VERSION, build_sarif, write_sarif
from tool_semantics.scanner import capture_manifest, write_snapshot

runner = CliRunner()


def _report() -> CompatibilityReport:
    return CompatibilityReport(
        baseline="demo@1",
        candidate="demo@2",
        changes=[
            Change(
                severity=Severity.BREAKING,
                code="tool.removed",
                subject="search_issues",
                message="Tool 'search_issues' was removed.",
            ),
            Change(
                severity=Severity.INFO,
                code="tool.added",
                subject="list_labels",
                message="Tool 'list_labels' was added.",
            ),
            Change(
                severity=Severity.WARNING,
                code="tool.description_changed",
                subject="create_issue",
                message="Description changed.",
            ),
            Change(
                severity=Severity.CRITICAL,
                code="tool.risk_changed",
                subject="delete_repo",
                message="Risk escalated.",
            ),
        ],
    )


def test_sarif_schema_smoke(tmp_path: Path) -> None:
    report = _report()
    payload = build_sarif(report)
    assert payload["$schema"] == SARIF_SCHEMA
    assert payload["version"] == SARIF_VERSION
    run = payload["runs"][0]
    assert run["tool"]["driver"]["name"] == "tool-semantics"
    # Default: breaking + critical only (not info/warning).
    assert len(run["results"]) == 2
    levels = {item["level"] for item in run["results"]}
    assert levels == {"error"}
    rule_ids = {item["ruleId"] for item in run["results"]}
    assert rule_ids == {"tool.removed", "tool.risk_changed"}
    for result in run["results"]:
        assert "ruleIndex" in result
        assert 0 <= result["ruleIndex"] < len(run["tool"]["driver"]["rules"])

    with_warnings = build_sarif(report, include_warnings=True)
    assert len(with_warnings["runs"][0]["results"]) == 3

    out = tmp_path / "report.sarif"
    write_sarif(report, out)
    loaded = json.loads(out.read_text(encoding="utf-8"))
    assert loaded["version"] == "2.1.0"
    assert loaded["runs"][0]["properties"]["is_compatible"] is False


def test_html_contains_scorecard_and_findings() -> None:
    html = render_html_report(_report())
    assert "<!DOCTYPE html>" in html
    assert "Scorecard" in html
    assert "Findings" in html
    assert "tool.removed" in html
    assert "search_issues" in html
    assert "breaking" in html
    assert 'class="badge fail">' in html
    assert ">breaking<" in html
    assert "Critical" in html
    # No JS framework dependency.
    assert "react" not in html.lower()
    assert "<script" not in html.lower()


def test_compare_cli_sarif_html(tmp_path: Path) -> None:
    baseline = tmp_path / "v1.json"
    candidate = tmp_path / "v2.json"
    write_snapshot(capture_manifest(Path("examples/github_server_v1.json")), baseline)
    write_snapshot(capture_manifest(Path("examples/github_server_v2.json")), candidate)
    sarif_path = tmp_path / "out.sarif"
    html_path = tmp_path / "out.html"
    result = runner.invoke(
        app,
        [
            "compare",
            str(baseline),
            str(candidate),
            "--sarif-output",
            str(sarif_path),
            "--html-output",
            str(html_path),
            "--policy",
            "permissive",
        ],
    )
    assert result.exit_code in {0, 1}, result.output
    assert sarif_path.is_file()
    assert html_path.is_file()
    payload = json.loads(sarif_path.read_text(encoding="utf-8"))
    assert payload["version"] == "2.1.0"
    assert "Scorecard" in html_path.read_text(encoding="utf-8")
