"""Tests for compatibility scorecard (#77)."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from tool_semantics.cli import app
from tool_semantics.diff import Change, CompatibilityReport, Severity, compare_snapshots
from tool_semantics.scanner import capture_manifest, write_snapshot
from tool_semantics.scorecard import (
    DimensionName,
    DimensionStatus,
    EvidenceLabel,
    build_scorecard,
    explain_change,
    render_pr_comment_markdown,
    render_scorecard_markdown,
)

runner = CliRunner()


def test_missing_behavioral_data_is_na_not_zero() -> None:
    report = CompatibilityReport(baseline="a", candidate="b", changes=[])
    card = build_scorecard(report, behavioral_ran=False, stability_ran=False)
    by_name = {dim.name: dim for dim in card.dimensions}
    assert by_name[DimensionName.BEHAVIORAL].status is DimensionStatus.NA
    assert by_name[DimensionName.BEHAVIORAL].score is None
    assert by_name[DimensionName.STABILITY].score is None
    assert "not 0%" in by_name[DimensionName.BEHAVIORAL].note
    assert card.final_result == "PASS"


def test_critical_safety_forces_final_fail() -> None:
    report = CompatibilityReport(
        baseline="a",
        candidate="b",
        changes=[
            Change(
                severity=Severity.INFO,
                code="tool.added",
                subject="x",
                message="added",
            ),
            Change(
                severity=Severity.CRITICAL,
                code="tool.risk_changed",
                subject="delete",
                message="read_only → destructive",
            ),
        ],
    )
    card = build_scorecard(report)
    assert card.final_result == "FAIL"
    assert card.forced_fail
    assert card.forced_fail_reason and "Critical safety" in card.forced_fail_reason
    safety = next(dim for dim in card.dimensions if dim.name is DimensionName.SAFETY)
    assert safety.status is DimensionStatus.FAIL


def test_explanations_label_deterministic_and_include_remediation() -> None:
    change = Change(
        severity=Severity.BREAKING,
        code="tool.removed",
        subject="search_issues",
        message="Tool 'search_issues' was removed.",
    )
    explanation = explain_change(change)
    assert explanation.evidence is EvidenceLabel.DETERMINISTIC
    assert "Agents" in explanation.why_it_matters
    assert explanation.remediation


def test_behavior_codes_mark_model_based_and_enable_dimension() -> None:
    report = CompatibilityReport(
        baseline="a",
        candidate="b",
        changes=[
            Change(
                severity=Severity.BREAKING,
                code="behavior.tool_selection_failed",
                subject="p1",
                message="wrong tool",
            )
        ],
    )
    card = build_scorecard(report)
    behavioral = next(dim for dim in card.dimensions if dim.name is DimensionName.BEHAVIORAL)
    assert behavioral.status is DimensionStatus.FAIL
    assert behavioral.score is not None
    assert behavioral.evidence is EvidenceLabel.MODEL_BASED
    assert card.explanations[0].evidence is EvidenceLabel.MODEL_BASED


def test_scorecard_markdown_and_compare_cli(tmp_path: Path) -> None:
    baseline = capture_manifest(Path("examples/github_server_v1.json"))
    candidate = capture_manifest(Path("examples/github_server_v2.json"))
    report = compare_snapshots(baseline, candidate)
    card = build_scorecard(report)
    md = render_scorecard_markdown(card)
    assert "## Compatibility scorecard" in md
    assert "**FINAL RESULT:** `FAIL`" in md
    assert "DETERMINISTIC" in md
    assert "Breaking / critical explanations" in md

    b = tmp_path / "v1.json"
    c = tmp_path / "v2.json"
    write_snapshot(baseline, b)
    write_snapshot(candidate, c)
    out_md = tmp_path / "r.md"
    out_js = tmp_path / "r.json"
    result = runner.invoke(
        app,
        [
            "compare",
            str(b),
            str(c),
            "--markdown-output",
            str(out_md),
            "--json-output",
            str(out_js),
        ],
    )
    assert result.exit_code == 1
    text = out_md.read_text(encoding="utf-8")
    assert "Compatibility scorecard" in text
    payload = json.loads(out_js.read_text(encoding="utf-8"))
    assert payload["scorecard"]["final_result"] == "FAIL"
    dims = payload["scorecard"]["dimensions"]
    assert any(dim["name"] == "behavioral" and dim["score"] is None for dim in dims)


def test_pr_comment_structural_only_when_probes_omitted() -> None:
    report = CompatibilityReport(
        baseline="a",
        candidate="b",
        changes=[
            Change(
                severity=Severity.BREAKING,
                code="tool.removed",
                subject="search_issues",
                message="Tool 'search_issues' was removed.",
            )
        ],
    )
    card = build_scorecard(report)
    payload = {
        "counts": report.counts_by_severity(),
        "scorecard": card.to_json(),
        "probes": {"enabled": False, "failed": False},
        "policy": {"probe_failed": False},
    }
    comment = render_pr_comment_markdown(
        report_payload=payload,
        full_report_markdown="# full report\n",
    )
    assert "## Tool-Semantics eval summary" in comment
    assert "**STATUS:** `FAIL`" in comment
    assert "### Counts" in comment
    assert "### Scorecard" in comment
    assert "`behavioral`" in comment
    assert "n/a" in comment
    assert "structural-only summary" in comment
    assert "### Top breaking findings" in comment
    assert "`tool.removed` on `search_issues`" in comment
    assert "<details>" in comment
    assert "full report" in comment


def test_pr_comment_probe_failure_forces_status_fail() -> None:
    report = CompatibilityReport(baseline="a", candidate="b", changes=[])
    card = build_scorecard(report, behavioral_ran=True, stability_ran=False)
    payload = {
        "counts": report.counts_by_severity(),
        "scorecard": card.to_json(),
        "probes": {"enabled": True, "failed": True},
        "policy": {"probe_failed": True},
    }
    comment = render_pr_comment_markdown(report_payload=payload)
    assert "**STATUS:** `FAIL`" in comment
    assert "Probe gate failed" in comment
    assert "structural-only summary" not in comment


def test_pr_comment_fixture_snapshot() -> None:
    """Stable fixture snapshot of the eval-style PR comment (#78)."""
    report = CompatibilityReport(
        baseline="baseline",
        candidate="candidate",
        changes=[
            Change(
                severity=Severity.BREAKING,
                code="tool.removed",
                subject="search_issues",
                message="Tool 'search_issues' was removed.",
            ),
            Change(
                severity=Severity.CRITICAL,
                code="tool.risk_changed",
                subject="delete_repo",
                message="read_only → destructive",
            ),
            Change(
                severity=Severity.WARNING,
                code="tool.description_changed",
                subject="list_prs",
                message="description text changed",
            ),
        ],
    )
    card = build_scorecard(report)
    payload = {
        "counts": report.counts_by_severity(),
        "scorecard": card.to_json(),
        "probes": {"enabled": False},
        "policy": {"probe_failed": False},
    }
    comment = render_pr_comment_markdown(report_payload=payload)
    expected = (
        "## Tool-Semantics eval summary\n"
        "\n"
        "**STATUS:** `FAIL`\n"
        "\n"
        "### Counts\n"
        "\n"
        "- critical: `1`\n"
        "- breaking: `1`\n"
        "- warning: `1`\n"
        "- info: `0`\n"
        "\n"
        "### Scorecard\n"
        "\n"
        "| Dimension | Status | Score | Evidence |\n"
        "| --- | --- | ---: | --- |\n"
        "| `structural` | `fail` | 0% | `DETERMINISTIC` |\n"
        "| `semantic` | `warning` | 75% | `DETERMINISTIC` |\n"
        "| `behavioral` | `n/a` | n/a | `N/A` |\n"
        "| `safety` | `fail` | 0% | `DETERMINISTIC` |\n"
        "| `stability` | `n/a` | n/a | `N/A` |\n"
        "\n"
        "_Behavioral / stability probes were not configured — "
        "structural-only summary (behavioral/stability show n/a)._\n"
        "\n"
        "### Safety\n"
        "\n"
        "**Safety status:** `fail` (breaking/critical risk changes).\n"
        "\n"
        "### Top breaking findings\n"
        "\n"
        "- `tool.removed` on `search_issues` (`DETERMINISTIC`) — "
        "Tool 'search_issues' was removed.\n"
        "- `tool.risk_changed` on `delete_repo` (`DETERMINISTIC`) — "
        "read_only → destructive\n"
    )
    assert comment == expected
