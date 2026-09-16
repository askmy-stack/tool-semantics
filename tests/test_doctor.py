"""Tests for tool-semantics doctor (#96)."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from tool_semantics.cli import app
from tool_semantics.doctor import CheckStatus, run_doctor
from tool_semantics.project import scaffold_project
from tool_semantics.scanner import capture_manifest, write_snapshot


def test_doctor_happy_path_after_init(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("TOOL_SEMANTICS_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    scaffold_project(tmp_path)
    snapshot = capture_manifest(Path("examples/github_server_v1.json"))
    write_snapshot(snapshot, tmp_path / ".tool-semantics" / "baselines" / "baseline.json")
    report = run_doctor(tmp_path)
    assert report.ok
    by_name = {check.name: check for check in report.checks}
    assert by_name["python"].status == CheckStatus.OK
    assert by_name["install"].status == CheckStatus.OK
    assert by_name["config"].status == CheckStatus.OK
    assert by_name["layout"].status == CheckStatus.OK
    assert by_name["baselines"].status == CheckStatus.OK
    assert by_name["probes"].status == CheckStatus.OK
    assert by_name["model"].status == CheckStatus.WARNING


def test_doctor_errors_on_invalid_baseline(tmp_path: Path) -> None:
    scaffold_project(tmp_path)
    bad = tmp_path / ".tool-semantics" / "baselines" / "broken.json"
    bad.write_text("{not-json\n", encoding="utf-8")
    report = run_doctor(tmp_path)
    assert not report.ok
    assert any(
        check.name == "baselines" and check.status == CheckStatus.ERROR for check in report.checks
    )


def test_doctor_cli_exit_codes(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("TOOL_SEMANTICS_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    runner = CliRunner()
    # Empty dir → warnings only → exit 0
    result = runner.invoke(app, ["doctor", "--path", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert "warning" in result.output

    scaffold_project(tmp_path)
    bad = tmp_path / ".tool-semantics" / "baselines" / "broken.json"
    bad.write_text(json.dumps({"tools": "nope"}), encoding="utf-8")
    result_err = runner.invoke(app, ["doctor", "--path", str(tmp_path)])
    assert result_err.exit_code == 1, result_err.output
