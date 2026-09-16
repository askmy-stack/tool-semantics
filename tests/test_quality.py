"""Tests for lint / audit quality commands (#97)."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from tool_semantics.cli import app
from tool_semantics.quality import FindingSeverity, audit_snapshot, lint_snapshot
from tool_semantics.scanner import capture_manifest, write_snapshot


def test_lint_flags_bad_fixture() -> None:
    snapshot = capture_manifest(Path("examples/quality_bad_server.json"))
    report = lint_snapshot(snapshot)
    codes = {item.code for item in report.findings}
    assert "lint.missing_description" in codes
    assert "lint.vague_description" in codes
    assert "lint.duplicate_description" in codes
    assert "lint.poor_name" in codes
    assert "lint.risk_description_mismatch" in codes
    assert "lint.schema_description_mismatch" in codes
    assert report.error_count >= 1
    assert report.should_fail()


def test_audit_aggregates_and_ambiguous_pairs() -> None:
    snapshot = capture_manifest(Path("examples/quality_bad_server.json"))
    report = audit_snapshot(snapshot)
    assert report.tool_count == 4
    assert report.missing_description_count >= 1
    assert report.vague_description_count >= 1
    assert any(
        {pair.left, pair.right} == {"search_items", "find_items"} for pair in report.ambiguous_pairs
    )


def test_lint_cli_exit_policy(tmp_path: Path) -> None:
    snapshot = capture_manifest(Path("examples/quality_bad_server.json"))
    path = tmp_path / "bad.json"
    write_snapshot(snapshot, path)
    runner = CliRunner()
    fail = runner.invoke(app, ["lint", str(path)])
    assert fail.exit_code == 1, fail.output
    good = capture_manifest(Path("examples/github_server_v1.json"))
    good_path = tmp_path / "good.json"
    write_snapshot(good, good_path)
    ok = runner.invoke(app, ["lint", str(good_path)])
    # github demo may still have info unknown_risk only — should not fail by default
    assert ok.exit_code == 0, ok.output
    assert not any(item.severity == FindingSeverity.ERROR for item in lint_snapshot(good).findings)


def test_audit_cli(tmp_path: Path) -> None:
    snapshot = capture_manifest(Path("examples/quality_bad_server.json"))
    path = tmp_path / "bad.json"
    write_snapshot(snapshot, path)
    result = CliRunner().invoke(
        app, ["audit", str(path), "--markdown-output", str(tmp_path / "a.md")]
    )
    assert result.exit_code == 1, result.output
    assert (tmp_path / "a.md").is_file()
