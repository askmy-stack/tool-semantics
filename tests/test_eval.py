"""Tests for unified `tool-semantics eval` (#76)."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from tool_semantics.cli import app
from tool_semantics.diff import Change, CompatibilityReport, Severity
from tool_semantics.eval_report import (
    SAFETY_CODES,
    SEMANTIC_CODES,
    build_eval_report,
    partition_changes,
    render_eval_markdown,
)
from tool_semantics.policy import ReleasePolicy
from tool_semantics.probe_gate import ProbeGateReport
from tool_semantics.scanner import capture_manifest, write_snapshot

runner = CliRunner()
ROOT = Path(__file__).resolve().parents[1]
PROBES_OK = ROOT / "examples" / "probes" / "github_v1_offline.json"
MANIFEST_V1 = ROOT / "examples" / "github_server_v1.json"
MANIFEST_V2 = ROOT / "examples" / "github_server_v2.json"


def test_partition_changes_by_section() -> None:
    report = CompatibilityReport(
        baseline="a",
        candidate="b",
        changes=[
            Change(
                severity=Severity.BREAKING,
                code="tool.removed",
                subject="x",
                message="gone",
            ),
            Change(
                severity=Severity.WARNING,
                code="tool.description_changed",
                subject="y",
                message="desc",
            ),
            Change(
                severity=Severity.CRITICAL,
                code="tool.risk_changed",
                subject="z",
                message="risk",
            ),
            Change(
                severity=Severity.WARNING,
                code="tool.renamed",
                subject="a→b",
                message="rename",
            ),
        ],
    )
    structural, semantic, safety = partition_changes(report)
    assert [c.code for c in structural.changes] == ["tool.removed"]
    assert {c.code for c in semantic.changes} <= SEMANTIC_CODES
    assert {c.code for c in safety.changes} <= SAFETY_CODES
    assert len(semantic.changes) == 2
    assert len(safety.changes) == 1


def test_build_and_render_eval_report() -> None:
    report = CompatibilityReport(
        baseline="base",
        candidate="cand",
        changes=[
            Change(
                severity=Severity.WARNING,
                code="tool.description_changed",
                subject="t",
                message="changed",
            )
        ],
    )
    eval_report = build_eval_report(
        report,
        release_policy=ReleasePolicy(),
        probe_gate=ProbeGateReport(enabled=False),
    )
    assert eval_report.passed
    assert eval_report.final_result == "PASS"
    md = render_eval_markdown(eval_report)
    assert "## Structural" in md
    assert "## Semantic" in md
    assert "## Safety" in md
    assert "## Behavioral probes" in md
    assert "## Stability" in md
    assert "## FINAL RESULT" in md
    assert "**FINAL RESULT:** `PASS`" in md
    payload = eval_report.to_json()
    assert payload["kind"] == "eval"
    assert payload["sections"]["semantic"]["warnings"] == 1


def test_eval_cli_structural_fail(tmp_path: Path) -> None:
    baseline = tmp_path / "v1.json"
    candidate = tmp_path / "v2.json"
    write_snapshot(capture_manifest(MANIFEST_V1), baseline)
    write_snapshot(capture_manifest(MANIFEST_V2), candidate)
    js = tmp_path / "eval.json"
    md = tmp_path / "eval.md"
    result = runner.invoke(
        app,
        [
            "eval",
            "--baseline",
            str(baseline),
            "--candidate",
            str(candidate),
            "--json-output",
            str(js),
            "--markdown-output",
            str(md),
        ],
    )
    assert result.exit_code == 1, result.stdout
    assert "FINAL RESULT" in result.stdout
    assert "FAIL" in result.stdout
    payload = json.loads(js.read_text(encoding="utf-8"))
    assert payload["kind"] == "eval"
    assert payload["passed"] is False
    assert payload["sections"]["structural"]["breaking"] >= 1
    text = md.read_text(encoding="utf-8")
    assert "## Structural" in text
    assert "**FINAL RESULT:** `FAIL`" in text


def test_eval_cli_pass_with_offline_probes(tmp_path: Path) -> None:
    same = tmp_path / "same.json"
    write_snapshot(capture_manifest(MANIFEST_V1), same)
    js = tmp_path / "eval.json"
    result = runner.invoke(
        app,
        [
            "eval",
            "--baseline",
            str(same),
            "--candidate",
            str(same),
            "--probes",
            str(PROBES_OK),
            "--probe-mode",
            "offline",
            "--json-output",
            str(js),
        ],
    )
    assert result.exit_code == 0, result.stdout
    assert "PASS" in result.stdout
    payload = json.loads(js.read_text(encoding="utf-8"))
    assert payload["passed"] is True
    assert payload["probes"]["enabled"] is True
    assert payload["probes"]["failed"] is False


def test_eval_cli_probe_fail_under_permissive_policy(tmp_path: Path) -> None:
    same = tmp_path / "same.json"
    write_snapshot(capture_manifest(MANIFEST_V1), same)
    bad = tmp_path / "bad.json"
    bad.write_text(
        json.dumps(
            {
                "probes": [
                    {
                        "id": "missing",
                        "intent": "x",
                        "kind": "positive",
                        "expected_tool": "nope",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    result = runner.invoke(
        app,
        [
            "eval",
            "--baseline",
            str(same),
            "--candidate",
            str(same),
            "--probes",
            str(bad),
            "--policy",
            "permissive",
        ],
    )
    assert result.exit_code == 1
    assert "FAIL" in result.stdout


def test_eval_missing_snapshot_exit_2(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        [
            "eval",
            "--baseline",
            str(tmp_path / "missing.json"),
            "--candidate",
            str(tmp_path / "also-missing.json"),
        ],
    )
    assert result.exit_code == 2
